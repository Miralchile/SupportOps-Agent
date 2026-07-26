import sys
import types
import unittest
from unittest import mock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from service.supportops import workflow


class FakeDB:
    def close(self):
        pass


class SupportOpsWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.support_agent = types.ModuleType("service.supportops.support_agent")
        self.support_agent.search_support_docs = lambda *_: [
            {"document_id": "doc-1", "document_name": "faq", "content": "answer", "score": 1.0}
        ]
        self.support_agent._write_final_to_history = lambda *_: None
        self.ticket_search = types.ModuleType("service.supportops.similar_ticket_search")
        self.ticket_search.search_similar_tickets = lambda *_, **__: []
        self.modules = mock.patch.dict(sys.modules, {
            "service.supportops.support_agent": self.support_agent,
            "service.supportops.similar_ticket_search": self.ticket_search,
        })
        self.modules.start()
        self.trace_patch = mock.patch.object(workflow, "_record_trace", lambda *_: None)
        self.trace_patch.start()
        self.common = [
            mock.patch.object(workflow, "make_plan", lambda *_: {
                "routes": ["rag_search", "similar_ticket_search"], "tools": [], "reason": "test"
            }),
            mock.patch.object(workflow, "classify_intent", lambda *_: {
                "category": "product", "intent": "product_inquiry", "confidence": 0.9, "reason": "test"
            }),
            mock.patch.object(workflow, "check_escalation", lambda *_: {
                "need_human": False, "risk_level": "low", "reason": "safe", "matched_rules": []
            }),
            mock.patch.object(workflow, "generate_response", lambda *_: {
                "reply": "resolved", "summary": "ok", "next_action": "自动回复", "citations": []
            }),
            mock.patch.object(workflow, "reflect_response", lambda *_: {
                "missing_knowledge": False, "low_confidence": False, "high_risk": False,
                "need_follow_up": False, "must_human": False, "reason": "ok"
            }),
        ]
        for patcher in self.common:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.common):
            patcher.stop()
        self.trace_patch.stop()
        self.modules.stop()

    def build(self, thread="test"):
        graph = workflow.build_supportops_graph(InMemorySaver())
        config = {"configurable": {"thread_id": thread}}
        context = workflow.SupportOpsRuntimeContext(db_factory=FakeDB)
        return graph, config, context

    def test_happy_path_produces_structured_final_answer(self):
        graph, config, context = self.build("happy")
        list(graph.stream(
            workflow.new_turn_state("u1", "s1", "how to use it"),
            config,
            context=context,
            stream_mode="updates",
        ))
        final = graph.get_state(config).values["final_answer"]
        self.assertEqual(final["reply"], "resolved")
        self.assertEqual(final["workflow"], "langgraph")
        self.assertEqual(final["retry_count"], 0)
        self.assertIn("rag_search", [item["tool_name"] for item in final["agent_trace"]])

    def test_missing_evidence_rewrites_query_once(self):
        graph, config, context = self.build("retry")
        calls = []

        def search(*_):
            calls.append(True)
            if len(calls) == 1:
                return []
            return [{"document_id": "doc-2", "document_name": "faq", "content": "found", "score": 1.0}]

        self.support_agent.search_support_docs = search
        with mock.patch.object(workflow, "reflect_response", side_effect=lambda *args: {
            "missing_knowledge": not bool(args[2]),
            "low_confidence": False,
            "high_risk": False,
            "need_follow_up": not bool(args[2]),
            "must_human": False,
            "reason": "retry" if not args[2] else "ok",
        }), mock.patch.object(workflow, "rewrite_query", return_value={"query": "rewritten", "reason": "test"}):
            list(graph.stream(
                workflow.new_turn_state("u1", "s2", "ambiguous"),
                config,
                context=context,
                stream_mode="updates",
            ))
        final = graph.get_state(config).values["final_answer"]
        self.assertEqual(final["retry_count"], 1)
        self.assertEqual(len(calls), 2)

    def test_planned_tools_execute_and_unplanned_routes_skip(self):
        graph, config, context = self.build("tools")
        with mock.patch.object(workflow, "make_plan", return_value={
            "routes": ["rag_search"],
            "tools": [{"name": "query_logistics", "args": {"order_id": "ORD123456"}}],
            "reason": "tool test",
        }):
            list(graph.stream(
                workflow.new_turn_state("u1", "s4", "订单 ORD123456 物流到哪了"),
                config,
                context=context,
                stream_mode="updates",
            ))
        final = graph.get_state(config).values["final_answer"]
        self.assertEqual(final["tool_results"][0]["tool"], "query_logistics")
        self.assertEqual(final["tool_results"][0]["status"], "ok")
        self.assertEqual(final["plan"]["routes"], ["rag_search"])
        traces = {item["tool_name"]: item for item in final["agent_trace"]}
        self.assertIn("business_tools", traces)
        self.assertEqual(traces["similar_ticket_search"]["status"], "skipped")
        self.assertEqual(final["similar_tickets"], [])

    def test_high_risk_interrupt_can_be_edited_and_resumed(self):
        graph, config, context = self.build("human")
        with mock.patch.object(workflow, "check_escalation", return_value={
            "need_human": True, "risk_level": "high", "reason": "refund", "matched_rules": ["refund"]
        }), mock.patch.object(workflow, "reflect_response", return_value={
            "missing_knowledge": False, "low_confidence": False, "high_risk": True,
            "need_follow_up": False, "must_human": True, "reason": "risk"
        }):
            events = list(graph.stream(
                workflow.new_turn_state("u1", "s3", "refund"),
                config,
                context=context,
                stream_mode="updates",
            ))
            self.assertTrue(any("__interrupt__" in event for event in events))
            list(graph.stream(
                Command(resume={"action": "edit", "edited_reply": "human reviewed"}),
                config,
                context=context,
                stream_mode="updates",
            ))
        final = graph.get_state(config).values["final_answer"]
        self.assertEqual(final["reply"], "human reviewed")
        self.assertEqual(final["human_decision"]["action"], "edit")
        self.assertTrue(final["need_human"])


if __name__ == "__main__":
    unittest.main()
