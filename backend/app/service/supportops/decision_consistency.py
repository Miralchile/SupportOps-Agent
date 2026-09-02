"""Detect planner/intent conflicts before tools and retrieval execute."""

from __future__ import annotations

from typing import Any, Dict, List


INTENT_TOOL_EXPECTATIONS = {
    "delivery_status": {"query_logistics", "query_order"},
    "refund_request": {"check_refund_eligibility", "query_order"},
    "payment_failed": {"query_order"},
}


def check_decision_consistency(plan: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(classification.get("intent") or "general_inquiry")
    tools = {str(item.get("name")) for item in (plan.get("tools") or []) if isinstance(item, dict)}
    expected = INTENT_TOOL_EXPECTATIONS.get(intent, set())
    conflicts: List[str] = []

    if tools and expected and tools.isdisjoint(expected):
        conflicts.append(f"intent={intent} 与工具 {sorted(tools)} 不一致")
    if intent == "delivery_status" and "rag_search" not in (plan.get("routes") or []) and not tools:
        conflicts.append("物流意图既未规划业务工具，也未保留知识检索")

    return {
        "consistent": not conflicts,
        "conflicts": conflicts,
        "intent": intent,
        "planned_tools": sorted(tools),
        "expected_tools": sorted(expected),
    }
