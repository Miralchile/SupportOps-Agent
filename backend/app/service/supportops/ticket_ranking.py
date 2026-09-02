"""Metadata-aware ranking independent of Elasticsearch transport."""

from __future__ import annotations

import datetime
import math
from typing import Any, Dict, Iterable, List

from service.supportops.tools import keyword_category_intent


def _query_language(question: str) -> str:
    return "zh" if any("\u4e00" <= char <= "\u9fff" for char in question) else "en"


def rerank_ticket_candidates(
    question: str,
    tickets: Iterable[Any],
    base_scores: Dict[int, float],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Rank hybrid recall candidates using relevance and governance metadata."""
    inferred = keyword_category_intent(question)
    query_category = inferred.get("category")
    query_intent = inferred.get("intent")
    query_language = _query_language(question)
    now = datetime.datetime.now()
    ranked = []
    for ticket in tickets:
        base_score = min(max(float(base_scores.get(ticket.id, 0.0)), 0.0), 1.0)
        quality = min(max(float(ticket.quality_score or 0.0), 0.0), 1.0)
        category_match = float(query_category != "general" and ticket.category == query_category)
        intent_match = float(query_intent != "general_inquiry" and ticket.intent == query_intent)
        language_match = float(ticket.language in {query_language, "unknown"})
        created_at = ticket.updated_at or ticket.created_at
        age_days = max(0.0, (now - created_at).total_seconds() / 86400) if created_at else 365.0
        recency = math.exp(-age_days / 365.0)
        rerank_score = (
            0.65 * base_score
            + 0.15 * quality
            + 0.10 * intent_match
            + 0.05 * category_match
            + 0.03 * language_match
            + 0.02 * recency
        )
        ranked.append((rerank_score, ticket, {
            "retrieval": round(base_score, 4),
            "quality": round(quality, 4),
            "intent_match": bool(intent_match),
            "category_match": bool(category_match),
            "language_match": bool(language_match),
            "recency": round(recency, 4),
        }))
    ranked.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    return [
        {
            "id": ticket.id,
            "instruction": ticket.instruction,
            "category": ticket.category,
            "intent": ticket.intent,
            "response": ticket.response,
            "score": round(score, 4),
            "retrieval_score": features["retrieval"],
            "ranking_features": features,
        }
        for score, ticket, features in ranked[:top_k]
    ]
