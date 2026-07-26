from typing import Any, Dict, List, Optional

from service.supportops.prompts import REFLECTION_PROMPT, RESPONSE_GENERATION_PROMPT
from service.supportops.tools import call_json_llm, compact


def _tool_based_fallback(tool_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a deterministic reply from tool results (no-LLM path)."""
    if not tool_results:
        return None
    by_tool = {item.get("tool"): item for item in tool_results if isinstance(item, dict)}

    missing = next((item for item in tool_results if item.get("status") == "missing_args"), None)
    if missing and all(item.get("status") in {"missing_args", "error"} for item in tool_results):
        return {
            "reply": "您好，为了帮您查询订单/物流状态，请提供订单号（例如 ORD123456）。",
            "summary": "工具调用缺少订单号，需要追问用户。",
            "next_action": "追问用户",
            "citations": [{"type": "tool", "id": missing.get("tool")}],
        }

    not_found = next((item for item in tool_results if item.get("status") == "not_found"), None)
    if not_found and not any(item.get("status") == "ok" for item in tool_results):
        return {
            "reply": f"您好，{not_found.get('message', '未查询到对应订单')}。请确认订单号后再试，或提供下单手机号便于人工核实。",
            "summary": "订单号未命中，提示用户核对。",
            "next_action": "追问用户",
            "citations": [{"type": "tool", "id": not_found.get("tool")}],
        }

    logistics = by_tool.get("query_logistics")
    if logistics and logistics.get("status") == "ok":
        checkpoint = (logistics.get("checkpoints") or [{}])[-1]
        reply = (
            f"您好，订单 {logistics.get('order_id')} 由{logistics.get('carrier')}承运，"
            f"当前状态为「{logistics.get('current_status')}」，"
            f"最新轨迹：{checkpoint.get('time', '')} {checkpoint.get('location', '')} {checkpoint.get('status', '')}。"
            "如长时间未更新，可回复我们协助催件。"
        )
        return {
            "reply": reply,
            "summary": "基于物流工具查询结果回复。",
            "next_action": "自动回复",
            "citations": [{"type": "tool", "id": "query_logistics"}],
        }

    refund = by_tool.get("check_refund_eligibility")
    if refund and refund.get("status") == "ok":
        if refund.get("eligible"):
            reply = (
                f"您好，订单 {refund.get('order_id')} 仍在 {refund.get('window_days')} 天退款窗口内"
                f"（已签收 {refund.get('days_since_receipt')} 天），可以直接发起自动退款。"
                "确认退款后金额将原路退回。"
            )
        else:
            reply = (
                f"您好，订单 {refund.get('order_id')} 已超出 {refund.get('window_days')} 天退款窗口"
                f"（已签收 {refund.get('days_since_receipt')} 天），需要人工审核特殊退款申请，"
                "我会为您登记并转交人工同事跟进。"
            )
        return {
            "reply": reply,
            "summary": "基于退款资格工具查询结果回复。",
            "next_action": "自动回复" if refund.get("eligible") else "转人工",
            "citations": [{"type": "tool", "id": "check_refund_eligibility"}],
        }

    order = by_tool.get("query_order")
    if order and order.get("status") == "ok":
        reply = (
            f"您好，订单 {order.get('order_id')} 当前状态为「{order.get('order_status')}」，"
            f"支付状态「{order.get('payment_status')}」，金额 {order.get('amount_cny')} 元，"
            f"下单日期 {order.get('created_at')}。如需进一步处理请告诉我。"
        )
        return {
            "reply": reply,
            "summary": "基于订单工具查询结果回复。",
            "next_action": "自动回复",
            "citations": [{"type": "tool", "id": "query_order"}],
        }
    return None


def _fallback_response(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    escalation: Dict[str, Any],
    tool_results: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if escalation.get("need_human"):
        reply = (
            "您好，已识别到该问题可能涉及较高风险场景。"
            "我会先记录您的诉求，并建议转人工客服继续核实处理。"
            "为便于人工同事跟进，请补充订单号、账号信息或相关截图。"
        )
        return {
            "reply": reply,
            "summary": f"识别为 {classification.get('category')} / {classification.get('intent')}，建议人工介入。",
            "next_action": "转人工",
            "citations": [],
        }

    tool_reply = _tool_based_fallback(tool_results or [])
    if tool_reply:
        return tool_reply

    citations = []
    if sources:
        citations.append({"type": "document", "id": sources[0].get("document_id"), "name": sources[0].get("document_name")})
    if similar_tickets:
        citations.append({"type": "ticket", "id": similar_tickets[0].get("id")})

    if similar_tickets:
        reply = similar_tickets[0].get("response") or ""
        if reply:
            return {
                "reply": reply,
                "summary": "基于最相似历史工单生成回复。",
                "next_action": "自动回复",
                "citations": citations,
            }

    if sources:
        reply = (
            "您好，根据当前知识库信息，建议您先参考以下处理方式："
            f"{sources[0].get('content', '')[:260]}。"
            "如果仍无法解决，请补充更多问题现象或截图。"
        )
        return {
            "reply": reply,
            "summary": "基于 FAQ / 产品文档生成回复。",
            "next_action": "自动回复",
            "citations": citations,
        }

    return {
        "reply": "您好，我还需要更多信息才能准确处理。请补充订单号、账号、报错截图或具体操作步骤。",
        "summary": "缺少知识库依据和相似历史工单，建议追问用户。",
        "next_action": "追问用户",
        "citations": citations,
    }


def generate_response(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    escalation: Dict[str, Any],
    messages: List[Dict[str, Any]] | None = None,
    tool_results: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fallback = _fallback_response(question, classification, sources, similar_tickets, escalation, tool_results)
    prompt = RESPONSE_GENERATION_PROMPT.format(
        question=question,
        history=compact((messages or [])[-6:]),
        classification=compact(classification),
        sources=compact(sources),
        similar_tickets=compact(similar_tickets),
        tool_results=compact(tool_results or []),
        escalation=compact(escalation),
    )
    result = call_json_llm(prompt, fallback)
    reply = result.get("reply") or fallback["reply"]
    next_action = result.get("next_action") or fallback["next_action"]
    if escalation.get("need_human"):
        next_action = "转人工"
    return {
        "reply": reply,
        "summary": result.get("summary") or fallback["summary"],
        "next_action": next_action,
        "citations": _normalize_citations(result.get("citations"), fallback["citations"]),
    }


def _normalize_citations(raw: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM 偶尔会把 citations 写成字符串数组；规范化为字典数组，
    避免单个字段的类型偏差让整份回复被校验层打回兜底。"""
    if not isinstance(raw, list):
        return fallback
    citations: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            citations.append(item)
        elif item is not None:
            citations.append({"type": "ref", "id": str(item)})
    return citations


def reflect_response(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    escalation: Dict[str, Any],
    generated_response: Dict[str, Any],
    messages: List[Dict[str, Any]] | None = None,
    tool_results: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    has_evidence = bool(sources or similar_tickets or any(
        item.get("status") == "ok" for item in (tool_results or []) if isinstance(item, dict)
    ))
    fallback = {
        "missing_knowledge": not has_evidence,
        "low_confidence": float(classification.get("confidence", 0.0)) < 0.55,
        "high_risk": escalation.get("risk_level") == "high",
        "need_follow_up": not has_evidence,
        "must_human": bool(escalation.get("need_human")),
        "reason": "基于证据数量（含工具结果）、分类置信度和风险规则的自动检查。",
    }
    prompt = REFLECTION_PROMPT.format(
        question=question,
        history=compact((messages or [])[-6:]),
        classification=compact(classification),
        sources=compact(sources),
        similar_tickets=compact(similar_tickets),
        tool_results=compact(tool_results or []),
        escalation=compact(escalation),
        generated_response=compact(generated_response),
    )
    result = call_json_llm(prompt, fallback)
    return {
        "missing_knowledge": bool(result.get("missing_knowledge", fallback["missing_knowledge"])),
        "low_confidence": bool(result.get("low_confidence", fallback["low_confidence"])),
        "high_risk": bool(result.get("high_risk", fallback["high_risk"])),
        "need_follow_up": bool(result.get("need_follow_up", fallback["need_follow_up"])),
        "must_human": bool(result.get("must_human", fallback["must_human"])),
        "reason": result.get("reason") or fallback["reason"],
    }
