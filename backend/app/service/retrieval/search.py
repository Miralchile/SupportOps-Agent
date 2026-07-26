"""Hybrid (keyword + vector) retrieval with weighted score fusion.

Keyword recall uses BM25 over the jieba-tokenized ``content_ltks`` /
``title_tks`` fields; vector recall uses ES kNN over the DashScope embedding.
Scores are fused client-side: ``(1 - w) * bm25_norm + w * cosine``. Without a
usable embedding the search transparently degrades to keyword-only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from service.retrieval.embedding import embedding_vector_field, generate_embedding
from service.retrieval.es_client import get_es, index_exists
from service.retrieval.text_utils import fine_grained_tokenize

logger = logging.getLogger("supportops.search")

_SOURCE_FIELDS = ["doc_id", "docnm_kwd", "content_with_weight"]


def hybrid_search(
    index_name: str,
    question: str,
    top_k: int = 5,
    vector_weight: float = 0.6,
) -> List[Dict[str, Any]]:
    """Return up to ``top_k`` chunks with ``similarity`` scores in [0, 1]."""
    question = (question or "").strip()
    if not question or not index_exists(index_name):
        return []

    recall_size = max(top_k * 3, 16)
    keyword_hits = _keyword_search(index_name, question, recall_size)
    vector_hits = _vector_search(index_name, question, recall_size)

    if not keyword_hits and not vector_hits:
        return []
    if not vector_hits:
        vector_weight = 0.0
    elif not keyword_hits:
        vector_weight = 1.0

    fused: Dict[str, Dict[str, Any]] = {}
    max_bm25 = max((hit["_score"] or 0.0 for hit in keyword_hits), default=0.0) or 1.0
    for hit in keyword_hits:
        entry = _entry(fused, hit)
        entry["keyword_score"] = max(entry["keyword_score"], (hit["_score"] or 0.0) / max_bm25)
    for hit in vector_hits:
        entry = _entry(fused, hit)
        # ES cosine kNN scores are (1 + cos) / 2, already within [0, 1].
        entry["vector_score"] = max(entry["vector_score"], hit["_score"] or 0.0)

    results = []
    for entry in fused.values():
        similarity = (1 - vector_weight) * entry["keyword_score"] + vector_weight * entry["vector_score"]
        source = entry["source"]
        results.append(
            {
                "chunk_id": entry["chunk_id"],
                "doc_id": source.get("doc_id") or "",
                "docnm_kwd": source.get("docnm_kwd") or "",
                "content_with_weight": source.get("content_with_weight") or "",
                "similarity": round(float(similarity), 4),
            }
        )
    results.sort(key=lambda item: item["similarity"], reverse=True)
    return results[:top_k]


def _entry(fused: Dict[str, Dict[str, Any]], hit: Dict[str, Any]) -> Dict[str, Any]:
    chunk_id = hit.get("_id")
    if chunk_id not in fused:
        fused[chunk_id] = {
            "chunk_id": chunk_id,
            "source": hit.get("_source") or {},
            "keyword_score": 0.0,
            "vector_score": 0.0,
        }
    return fused[chunk_id]


def _keyword_search(index_name: str, question: str, size: int) -> List[Dict[str, Any]]:
    tokens = fine_grained_tokenize(question)
    if not tokens:
        return []
    query = {
        "bool": {
            "should": [
                {"match": {"content_ltks": {"query": tokens, "minimum_should_match": "30%"}}},
                {"match": {"content_sm_ltks": {"query": tokens, "minimum_should_match": "30%"}}},
                {"match": {"title_tks": {"query": tokens, "boost": 4}}},
            ],
            "minimum_should_match": 1,
            "filter": [{"term": {"available_int": 1}}],
        }
    }
    try:
        response = get_es().search(index=index_name, query=query, size=size, source=_SOURCE_FIELDS)
        return list(response.get("hits", {}).get("hits", []))
    except Exception as exc:
        logger.warning("Keyword search on %s failed: %s", index_name, exc)
        return []


def _vector_search(index_name: str, question: str, size: int) -> List[Dict[str, Any]]:
    query_vector: Optional[List[float]] = None
    try:
        query_vector = generate_embedding(question)  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("Query embedding failed: %s", exc)
    if not query_vector:
        return []
    knn = {
        "field": embedding_vector_field(),
        "query_vector": query_vector,
        "k": size,
        "num_candidates": max(size * 4, 64),
        "filter": {"term": {"available_int": 1}},
    }
    try:
        response = get_es().search(index=index_name, knn=knn, size=size, source=_SOURCE_FIELDS)
        return list(response.get("hits", {}).get("hits", []))
    except Exception as exc:
        logger.warning("Vector search on %s failed: %s", index_name, exc)
        return []
