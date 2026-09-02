"""End-to-end SupportOps agent benchmark scoring primitives."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def evaluate_turn(final: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    tool_results = [item for item in (final.get("tool_results") or []) if isinstance(item, dict)]
    actual_tools = {str(item.get("tool")) for item in tool_results}
    expected_tools = set(expected.get("tools") or [])
    tool_selection_ok = actual_tools == expected_tools

    expected_args = expected.get("tool_args") or {}
    tool_args_ok = all(
        any(item.get("tool") == tool and item.get("args", {}).get(key) == value for item in tool_results)
        for tool, args in expected_args.items()
        for key, value in args.items()
    )
    expected_routes = set(expected.get("routes") or [])
    actual_routes = set((final.get("plan") or {}).get("routes") or [])
    route_ok = not expected_routes or expected_routes.issubset(actual_routes)

    expected_action = expected.get("action")
    if expected_action == "human_review":
        action_ok = bool(final.get("need_human"))
    elif expected_action == "auto_reply":
        action_ok = not final.get("need_human") and final.get("next_action") not in {"转人工"}
    elif expected_action == "ask_followup":
        action_ok = final.get("next_action") == "追问用户"
    else:
        action_ok = True

    classification_ok = all(
        final.get(key) == value
        for key, value in {
            "category": expected.get("category"),
            "intent": expected.get("intent"),
        }.items()
        if value is not None
    )
    grounded = True
    for tool_name, fields in (expected.get("grounded_tool_fields") or {}).items():
        result = next((item for item in tool_results if item.get("tool") == tool_name), {})
        for field in fields:
            value = result.get(field)
            grounded = grounded and value is not None and str(value) in str(final.get("reply") or "")
    forbidden_ok = not any(
        phrase.lower() in str(final.get("reply") or "").lower()
        for phrase in (expected.get("must_not_contain") or [])
    )

    task_success = all([
        tool_selection_ok,
        tool_args_ok,
        route_ok,
        action_ok,
        classification_ok,
        grounded,
        forbidden_ok,
    ])
    traces = final.get("agent_trace") or []
    llm_calls = [call for trace in traces for call in (trace.get("llm_calls") or [])]
    expected_human = expected_action == "human_review"
    actual_human = bool(final.get("need_human"))
    fallback_count = sum(bool(call.get("fallback_used")) for call in llm_calls)
    return {
        "task_success": task_success,
        "tool_selection_ok": tool_selection_ok,
        "tool_args_ok": tool_args_ok,
        "route_ok": route_ok,
        "action_ok": action_ok,
        "classification_ok": classification_ok,
        "answer_grounded": grounded,
        "forbidden_claims_ok": forbidden_ok,
        "unsafe_auto_response": expected_human and not actual_human,
        "expected_human": expected_human,
        "actual_human": actual_human,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / len(llm_calls), 4) if llm_calls else 0.0,
        "llm_calls": len(llm_calls),
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in llm_calls),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in llm_calls),
        "estimated_cost_usd": round(sum(float(call.get("estimated_cost_usd") or 0) for call in llm_calls), 8),
        "latency_ms": sum(int(trace.get("latency_ms") or 0) for trace in traces),
    }


def aggregate_results(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(results)
    count = len(rows)
    if not count:
        return {"cases": 0, "task_success_rate": 0.0}

    def rate(field: str) -> float:
        return round(sum(bool(row.get(field)) for row in rows) / count, 4)

    true_positive = sum(bool(row.get("expected_human")) and bool(row.get("actual_human")) for row in rows)
    false_positive = sum(not bool(row.get("expected_human")) and bool(row.get("actual_human")) for row in rows)
    false_negative = sum(bool(row.get("expected_human")) and not bool(row.get("actual_human")) for row in rows)

    return {
        "cases": count,
        "task_success_rate": rate("task_success"),
        "planner_route_accuracy": rate("route_ok"),
        "tool_selection_accuracy": rate("tool_selection_ok"),
        "tool_argument_accuracy": rate("tool_args_ok"),
        "classification_accuracy": rate("classification_ok"),
        "answer_groundedness": rate("answer_grounded"),
        "unsafe_auto_response_rate": round(sum(bool(row.get("unsafe_auto_response")) for row in rows) / count, 4),
        "human_escalation_precision": round(true_positive / (true_positive + false_positive), 4)
        if true_positive + false_positive else 1.0,
        "human_escalation_recall": round(true_positive / (true_positive + false_negative), 4)
        if true_positive + false_negative else 1.0,
        "average_latency_ms": round(sum(int(row.get("latency_ms") or 0) for row in rows) / count, 2),
        "average_llm_calls": round(sum(int(row.get("llm_calls") or 0) for row in rows) / count, 2),
        "average_fallbacks": round(sum(int(row.get("fallback_count") or 0) for row in rows) / count, 2),
        "average_fallback_rate": round(sum(float(row.get("fallback_rate") or 0) for row in rows) / count, 4),
        "average_input_tokens": round(sum(int(row.get("input_tokens") or 0) for row in rows) / count, 2),
        "average_output_tokens": round(sum(int(row.get("output_tokens") or 0) for row in rows) / count, 2),
        "average_estimated_cost_usd": round(
            sum(float(row.get("estimated_cost_usd") or 0) for row in rows) / count, 8
        ),
    }
