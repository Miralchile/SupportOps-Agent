import unittest

from service.supportops.business_tools import (
    check_refund_eligibility,
    execute_tool,
    extract_order_id,
    query_logistics,
    query_order,
)


class ExtractOrderIdTest(unittest.TestCase):
    def test_ord_pattern(self):
        self.assertEqual(extract_order_id("订单 ORD123456 到哪了"), "ORD123456")
        self.assertEqual(extract_order_id("I want my money back for order ORD888777"), "ORD888777")

    def test_labelled_fallback_pattern(self):
        self.assertEqual(extract_order_id("单号：AB12345678 麻烦查一下"), "AB12345678")

    def test_no_id(self):
        self.assertIsNone(extract_order_id("怎么导出我的数据"))
        self.assertIsNone(extract_order_id(""))


class MockToolsTest(unittest.TestCase):
    def test_query_order_is_deterministic(self):
        self.assertEqual(query_order("ORD123456"), query_order("ORD123456"))
        self.assertEqual(query_order("ORD123456")["status"], "ok")

    def test_not_found_convention(self):
        # digits ending in 00 simulate an unknown order
        for tool in (query_order, query_logistics, check_refund_eligibility):
            self.assertEqual(tool("ORD123400")["status"], "not_found")

    def test_logistics_checkpoints_are_consistent(self):
        result = query_logistics("ORD123456")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["current_status"], result["checkpoints"][-1]["status"])

    def test_refund_eligibility_fields(self):
        result = check_refund_eligibility("ORD123456")
        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["eligible"], bool)
        self.assertEqual(result["eligible"], result["days_since_receipt"] <= result["window_days"])


class ExecuteToolTest(unittest.TestCase):
    def test_missing_args(self):
        result = execute_tool("query_order", {})
        self.assertEqual(result["status"], "missing_args")

    def test_unknown_tool(self):
        result = execute_tool("rm_rf", {"order_id": "ORD123456"})
        self.assertEqual(result["status"], "error")

    def test_ok_path_wraps_tool_name_and_args(self):
        result = execute_tool("query_order", {"order_id": "ORD123456"})
        self.assertEqual(result["tool"], "query_order")
        self.assertEqual(result["args"], {"order_id": "ORD123456"})
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
