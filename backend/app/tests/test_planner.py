import unittest

from service.supportops.api_key_context import use_api_key_config
from service.supportops.planner import RETRIEVAL_ROUTES, _validate_plan, make_plan


def rules_only(fn):
    """Force the deterministic fallback path (no LLM) regardless of env."""
    def wrapper(*args, **kwargs):
        with use_api_key_config({"api_key": ""}):
            return fn(*args, **kwargs)
    return wrapper


class FallbackPlanTest(unittest.TestCase):
    @rules_only
    def test_logistics_question_with_order_id_schedules_tools(self):
        plan = make_plan("订单 ORD123456 的物流到哪了")
        names = [tool["name"] for tool in plan["tools"]]
        self.assertIn("query_logistics", names)
        self.assertIn("query_order", names)
        self.assertEqual(plan["tools"][0]["args"]["order_id"], "ORD123456")
        self.assertEqual(sorted(plan["routes"]), sorted(RETRIEVAL_ROUTES))

    @rules_only
    def test_refund_question_with_order_id_checks_eligibility(self):
        plan = make_plan("ORD888777 这单我要退款")
        names = [tool["name"] for tool in plan["tools"]]
        self.assertIn("check_refund_eligibility", names)

    @rules_only
    def test_no_order_id_means_no_tools(self):
        plan = make_plan("怎么导出我的数据")
        self.assertEqual(plan["tools"], [])
        self.assertEqual(sorted(plan["routes"]), sorted(RETRIEVAL_ROUTES))


class ValidatePlanTest(unittest.TestCase):
    def test_garbage_routes_fall_back_to_all(self):
        fallback = {"routes": list(RETRIEVAL_ROUTES), "tools": [], "reason": "fb"}
        plan = _validate_plan({"routes": ["hack_the_db"], "tools": []}, fallback, "q")
        self.assertEqual(sorted(plan["routes"]), sorted(RETRIEVAL_ROUTES))

    def test_unknown_tools_are_filtered_and_order_id_backfilled(self):
        fallback = {"routes": list(RETRIEVAL_ROUTES), "tools": [], "reason": "fb"}
        raw = {
            "routes": ["rag_search"],
            "tools": [
                {"name": "rm_rf", "args": {}},
                {"name": "query_order", "args": {}},
            ],
        }
        plan = _validate_plan(raw, fallback, "帮我看下订单 ORD123456")
        self.assertEqual(plan["routes"], ["rag_search"])
        self.assertEqual(len(plan["tools"]), 1)
        self.assertEqual(plan["tools"][0]["name"], "query_order")
        self.assertEqual(plan["tools"][0]["args"]["order_id"], "ORD123456")

    def test_non_dict_uses_fallback(self):
        fallback = {"routes": list(RETRIEVAL_ROUTES), "tools": [], "reason": "fb"}
        self.assertEqual(_validate_plan("not json", fallback, "q"), fallback)


if __name__ == "__main__":
    unittest.main()
