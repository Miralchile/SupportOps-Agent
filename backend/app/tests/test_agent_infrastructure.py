import datetime
import time
import unittest
from unittest import mock

from service.supportops.agent_benchmark import aggregate_results, evaluate_turn
from service.supportops.api_key_context import use_api_key_config
from service.supportops.business_tools import tool_registry
from service.supportops.context_builder import ContextBuilder, ContextConfig
from service.supportops.decision_consistency import check_decision_consistency
from service.supportops.llm_gateway import capture_llm_observations, gateway
from service.supportops.planner import make_plan
from service.supportops.ticket_ranking import rerank_ticket_candidates
from service.supportops.tool_runtime import ToolDefinition, ToolParameter, ToolRegistry


class ToolRuntimeTest(unittest.TestCase):
    def test_registry_owns_schema_and_standard_result(self):
        definition = tool_registry.get("query_order")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.input_schema["required"], ["order_id"])
        result = tool_registry.execute("query_order", {"order_id": "ORD123456"}).to_dict()
        self.assertEqual(result["tool_version"], "1.0.0")
        self.assertEqual(result["status"], "ok")
        self.assertIn("latency_ms", result)

    def test_side_effect_tool_requires_confirmation(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="apply_refund",
            description="test",
            handler=lambda order_id: {"status": "ok", "order_id": order_id},
            parameters=(ToolParameter("order_id", "string", "id"),),
            side_effect=True,
            requires_confirmation=True,
        ))
        denied = registry.execute("apply_refund", {"order_id": "ORD123456"})
        self.assertEqual(denied.error_code, "confirmation_required")
        allowed = registry.execute("apply_refund", {"order_id": "ORD123456"}, confirmed=True)
        self.assertEqual(allowed.status, "ok")

    def test_timeout_is_enforced_and_reported(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="slow_tool",
            description="slow",
            handler=lambda: (time.sleep(0.05) or {"status": "ok"}),
            timeout_seconds=0.001,
            retries=1,
        ))

        result = registry.execute("slow_tool", {})

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error_code, "tool_timeout")
        self.assertEqual(result.attempts, 2)

    def test_input_and_output_schemas_are_runtime_contracts(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="strict_tool",
            description="strict",
            handler=lambda order_id: {"status": "ok", "wrong": order_id},
            parameters=(ToolParameter("order_id", "string", "id"),),
            output_schema={"type": "object", "required": ["result"]},
        ))

        invalid_input = registry.execute("strict_tool", {"order_id": 123, "extra": True})
        invalid_output = registry.execute("strict_tool", {"order_id": "ORD123456"})

        self.assertEqual(invalid_input.error_code, "invalid_arguments")
        self.assertEqual(invalid_output.error_code, "invalid_tool_output")


class LLMGatewayTest(unittest.TestCase):
    def test_missing_key_records_explicit_fallback(self):
        with use_api_key_config({"api_key": ""}), capture_llm_observations() as observations:
            result = gateway.generate_json("prompt", {"ok": False}, prompt_version="test.v1")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.fallback_reason, "missing_or_placeholder_api_key")
        self.assertEqual(observations[0]["prompt_version"], "test.v1")

    def test_invalid_json_is_distinct_from_network_error(self):
        completion = mock.Mock()
        completion.choices = [mock.Mock(message=mock.Mock(content="not-json"))]
        completion.usage = None
        client = mock.Mock()
        client.chat.completions.create.return_value = completion
        with use_api_key_config({"api_key": "sk-test", "base_url": "https://example.invalid/v1"}), \
                mock.patch("service.supportops.llm_gateway.OpenAI", return_value=client):
            result = gateway.generate_json("prompt", {"ok": False})
        self.assertEqual(result.error_type, "json_decode_error")
        self.assertEqual(result.fallback_reason, "invalid_json")

    def test_schema_error_is_observable(self):
        completion = mock.Mock()
        completion.choices = [mock.Mock(message=mock.Mock(content='{"unexpected": true}'))]
        completion.usage = None
        client = mock.Mock()
        client.chat.completions.create.return_value = completion
        with use_api_key_config({"api_key": "sk-test"}), \
                mock.patch("service.supportops.llm_gateway.OpenAI", return_value=client):
            result = gateway.generate_json(
                "prompt", {"reply": "fallback"}, schema={"required": ["reply"]}
            )
        self.assertEqual(result.error_type, "schema_error")
        self.assertTrue(result.fallback_reason.startswith("schema_validation_failed"))


class ContextAndDecisionTest(unittest.TestCase):
    def test_context_inherits_order_entity_within_budget(self):
        builder = ContextBuilder(ContextConfig(max_tokens=120, recent_message_limit=8))
        context = builder.build(
            "那这个还能退款吗？",
            [
                {"role": "user", "content": "我的订单是 ORD123456"},
                {"role": "assistant", "content": "已记录订单号"},
            ],
        )
        self.assertEqual(context.resolved_entities["order_id"], "ORD123456")
        self.assertLessEqual(context.estimated_tokens, 120)
        with use_api_key_config({"api_key": ""}):
            plan = make_plan("那这个还能退款吗？", context=builder.render(context))
        self.assertEqual(plan["tools"][0]["args"]["order_id"], "ORD123456")

    def test_consistency_flags_conflicting_tool(self):
        result = check_decision_consistency(
            {"routes": ["rag_search"], "tools": [{"name": "check_refund_eligibility", "args": {}}]},
            {"intent": "delivery_status"},
        )
        self.assertFalse(result["consistent"])
        self.assertTrue(result["conflicts"])


class FakeTicket:
    def __init__(self, identifier, category, intent, quality):
        self.id = identifier
        self.instruction = f"ticket {identifier}"
        self.response = "response"
        self.category = category
        self.intent = intent
        self.quality_score = quality
        self.language = "zh"
        self.created_at = datetime.datetime.now()
        self.updated_at = datetime.datetime.now()


class RerankerAndBenchmarkTest(unittest.TestCase):
    def test_metadata_reranker_can_promote_intent_match(self):
        generic = FakeTicket(1, "general", "general_inquiry", 0.5)
        delivery = FakeTicket(2, "delivery", "delivery_status", 1.0)
        ranked = rerank_ticket_candidates("物流到哪了", [generic, delivery], {1: 0.9, 2: 0.8}, top_k=2)
        self.assertEqual(ranked[0]["id"], 2)
        self.assertTrue(ranked[0]["ranking_features"]["intent_match"])

    def test_agent_benchmark_scores_task_success_and_safety(self):
        final = {
            "category": "delivery",
            "intent": "delivery_status",
            "need_human": False,
            "next_action": "自动回复",
            "reply": "当前状态为运输中",
            "plan": {"routes": ["rag_search"]},
            "tool_results": [{
                "tool": "query_logistics", "args": {"order_id": "ORD123456"},
                "status": "ok", "current_status": "运输中",
            }],
            "agent_trace": [],
        }
        score = evaluate_turn(final, {
            "category": "delivery", "intent": "delivery_status", "tools": ["query_logistics"],
            "tool_args": {"query_logistics": {"order_id": "ORD123456"}},
            "routes": ["rag_search"], "action": "auto_reply",
            "grounded_tool_fields": {"query_logistics": ["current_status"]},
        })
        self.assertTrue(score["task_success"])
        summary = aggregate_results([score])
        self.assertEqual(summary["task_success_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
