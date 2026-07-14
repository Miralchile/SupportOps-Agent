from typing import Any, Dict, List

from service.supportops.prompts import ESCALATION_CHECK_PROMPT
from service.supportops.tools import call_json_llm, compact, match_risk_rules


def check_escalation(
    question: str,
    classification: Dict[str, Any],
    sources: List[Dict[str, Any]],
    similar_tickets: List[Dict[str, Any]],
    messages: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    matched_rules = match_risk_rules(question)
    classification_risk = []
    category = classification.get("category", "")
    intent = classification.get("intent", "")
    for label in (category, intent):
        if label in {"complaint", "refund", "payment_failed", "privacy", "account_security"}:
            classification_risk.append(label)

    hard_rules = sorted(set(matched_rules + classification_risk))
    fallback = {
        "need_human": bool(hard_rules),
        "risk_level": "high" if hard_rules else "low",
        "reason": "命中高风险规则，建议转人工。" if hard_rules else "未命中高风险规则，可自动处理。",
        "matched_rules": hard_rules,
    }

    prompt = ESCALATION_CHECK_PROMPT.format(
        question=question,
        history=compact((messages or [])[-6:]),
        classification=compact(classification),
        sources=compact(sources),
        similar_tickets=compact(similar_tickets),
    )
    result = call_json_llm(prompt, fallback)

    llm_rules = result.get("matched_rules") if isinstance(result.get("matched_rules"), list) else []
    final_rules = sorted(set(hard_rules + [str(rule) for rule in llm_rules]))
    risk_level = result.get("risk_level") if result.get("risk_level") in {"low", "medium", "high"} else fallback["risk_level"]
    if hard_rules:
        risk_level = "high"

    return {
        "need_human": bool(result.get("need_human")) or bool(hard_rules),
        "risk_level": risk_level,
        "reason": result.get("reason") or fallback["reason"],
        "matched_rules": final_rules,
    }
