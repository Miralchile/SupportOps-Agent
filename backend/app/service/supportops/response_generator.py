from typing import Any, Dict, List

from service.supportops.prompts import REFLECTION_PROMPT, RESPONSE_GENERATION_PROMPT
from service.supportops.tools import call_json_llm, compact


def _fallback_response(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    escalation: Dict[str, Any],
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
) -> Dict[str, Any]:
    fallback = _fallback_response(question, classification, sources, similar_tickets, escalation)
    prompt = RESPONSE_GENERATION_PROMPT.format(
        question=question,
        history=compact((messages or [])[-6:]),
        classification=compact(classification),
        sources=compact(sources),
        similar_tickets=compact(similar_tickets),
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
        "citations": result.get("citations") if isinstance(result.get("citations"), list) else fallback["citations"],
    }


def reflect_response(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    escalation: Dict[str, Any],
    generated_response: Dict[str, Any],
    messages: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fallback = {
        "missing_knowledge": not bool(sources),
        "low_confidence": float(classification.get("confidence", 0.0)) < 0.55,
        "high_risk": escalation.get("risk_level") == "high",
        "need_follow_up": not bool(sources or similar_tickets),
        "must_human": bool(escalation.get("need_human")),
        "reason": "基于证据数量、分类置信度和风险规则的自动检查。",
    }
    prompt = REFLECTION_PROMPT.format(
        question=question,
        history=compact((messages or [])[-6:]),
        classification=compact(classification),
        sources=compact(sources),
        similar_tickets=compact(similar_tickets),
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
