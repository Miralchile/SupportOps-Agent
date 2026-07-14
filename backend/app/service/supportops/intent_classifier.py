from typing import Any, Dict, List

from service.supportops.prompts import INTENT_CLASSIFIER_PROMPT
from service.supportops.tools import (
    call_json_llm,
    extract_known_labels,
    keyword_category_intent,
    normalize_label,
)


def classify_intent(
    question: str,
    similar_tickets: List[Dict[str, Any]] | None = None,
    messages: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fallback = keyword_category_intent(question)
    labels = extract_known_labels(similar_tickets or [])
    prompt = INTENT_CLASSIFIER_PROMPT.format(
        question=question,
        history=(messages or [])[-6:],
        known_labels=labels,
    )
    result = call_json_llm(prompt, fallback)

    category = normalize_label(result.get("category"), fallback["category"])
    intent = normalize_label(result.get("intent"), fallback["intent"])
    try:
        confidence = float(result.get("confidence", fallback["confidence"]))
    except (TypeError, ValueError):
        confidence = fallback["confidence"]

    confidence = min(max(confidence, 0.0), 1.0)
    return {
        "category": category,
        "intent": intent,
        "confidence": confidence,
        "reason": result.get("reason") or fallback["reason"],
    }
