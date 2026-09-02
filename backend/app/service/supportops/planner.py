"""Planner: decides retrieval routes and business-tool calls for a turn.

With a valid LLM key the plan comes from the model (validated against the
route/tool whitelists); without one, a deterministic fallback derives the
plan from the question text. Either way the decision is real: retrieval
nodes skip routes the plan excludes, and the tools node executes exactly the
planned calls.
"""

from __future__ import annotations

from typing import Any, Dict, List

from service.supportops.business_tools import TOOL_NAMES, extract_order_id, tool_specs_prompt
from service.supportops.prompts import PLANNER_PROMPT
from service.supportops.tools import call_json_llm, compact

RETRIEVAL_ROUTES = ("rag_search", "similar_ticket_search")


def _fallback_plan(question: str, context: str = "") -> Dict[str, Any]:
    """Deterministic plan with explicit missing-argument handling."""
    tools: List[Dict[str, Any]] = []
    order_id = extract_order_id(question) or extract_order_id(context)
    lowered = question.lower()
    logistics_topic = any(k in lowered for k in (
        "物流", "快递", "发货", "配送", "到哪", "签收", "delivery", "shipping", "package", "tracking",
    ))
    refund_topic = any(k in lowered for k in ("退款", "退钱", "退货", "refund", "money back"))
    order_topic = any(k in lowered for k in ("订单", "order", "支付", "扣款", "金额"))
    specific_lookup = order_id is not None or any(k in lowered for k in (
        "帮我查", "查一下", "查下", "我的订单", "这个订单", "这单", "到哪",
    ))
    if specific_lookup:
        if logistics_topic:
            tools.append({"name": "query_logistics", "args": {"order_id": order_id or ""}})
        if refund_topic:
            tools.append({"name": "check_refund_eligibility", "args": {"order_id": order_id or ""}})
        if order_id and (not tools or order_topic):
            tools.insert(0, {"name": "query_order", "args": {"order_id": order_id}})
    return {
        "routes": list(RETRIEVAL_ROUTES),
        "tools": tools,
        "reason": "规则规划：默认全量检索；具体订单查询按话题选择工具，缺少订单号时由工具契约触发追问。",
    }


def _validate_plan(raw: Any, fallback: Dict[str, Any], question: str, context: str = "") -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    routes = [r for r in (raw.get("routes") or []) if r in RETRIEVAL_ROUTES]
    if not routes:
        routes = list(RETRIEVAL_ROUTES)

    tools: List[Dict[str, Any]] = []
    for item in (raw.get("tools") or [])[:3]:
        if not isinstance(item, dict) or item.get("name") not in TOOL_NAMES:
            continue
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        order_id = str(args.get("order_id") or "").strip() or extract_order_id(question) or extract_order_id(context) or ""
        tools.append({"name": item["name"], "args": {"order_id": order_id}})

    return {
        "routes": routes,
        "tools": tools,
        "reason": str(raw.get("reason") or "").strip() or fallback["reason"],
    }


def make_plan(
    question: str,
    messages: List[Dict[str, Any]] | None = None,
    context: str = "",
) -> Dict[str, Any]:
    fallback = _fallback_plan(question, context)
    prompt = PLANNER_PROMPT.format(
        question=question,
        history=context or compact((messages or [])[-6:]),
        tool_specs=tool_specs_prompt(),
    )
    raw = call_json_llm(
        prompt,
        fallback,
        prompt_version="planner.v2",
        schema={"required": ["routes", "tools"], "properties": {
            "routes": {"type": "array"}, "tools": {"type": "array"},
        }},
    )
    return _validate_plan(raw, fallback, question, context)
