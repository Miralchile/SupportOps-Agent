"""Minimal Elasticsearch access layer for the SupportOps indexes."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

from service.retrieval.embedding import EMBEDDING_DIMENSIONS, embedding_vector_field

load_dotenv()

logger = logging.getLogger("supportops.es")

_lock = threading.Lock()
_client: Elasticsearch | None = None

# Field layout shared by the docs and tickets indexes. ``*_ltks`` fields hold
# pre-tokenized (jieba) text and use the whitespace analyzer so index-time and
# query-time tokenization match exactly.
SUPPORTOPS_INDEX_BODY: Dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "content_ltks": {"type": "text", "analyzer": "whitespace"},
            "content_sm_ltks": {"type": "text", "analyzer": "whitespace"},
            "title_tks": {"type": "text", "analyzer": "whitespace"},
            "content_with_weight": {"type": "text", "index": False},
            "doc_id": {"type": "keyword"},
            "kb_id": {"type": "keyword"},
            "docnm": {"type": "keyword"},
            "docnm_kwd": {"type": "keyword"},
            "category_kwd": {"type": "keyword"},
            "intent_kwd": {"type": "keyword"},
            "source_kwd": {"type": "keyword"},
            "available_int": {"type": "integer"},
            "create_time": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||strict_date_optional_time||epoch_millis",
            },
            "create_timestamp_flt": {"type": "float"},
            embedding_vector_field(): {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMENSIONS,
                "index": True,
                "similarity": "cosine",
            },
        }
    },
}


def get_es() -> Elasticsearch:
    """Process-wide Elasticsearch client (credentials via environment)."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                host = os.getenv("ES_HOST", "http://localhost:9200")
                username = os.getenv("ELASTIC_USERNAME", "elastic")
                password = os.getenv("ELASTIC_PASSWORD", "")
                kwargs: Dict[str, Any] = {
                    "request_timeout": 60,
                    "verify_certs": False,
                }
                if password:
                    kwargs["basic_auth"] = (username, password)
                logger.info("Connecting to Elasticsearch at %s", host)
                _client = Elasticsearch([host], **kwargs)
    return _client


def index_exists(index_name: str) -> bool:
    try:
        return bool(get_es().indices.exists(index=index_name))
    except Exception as exc:
        logger.warning("Elasticsearch exists(%s) failed: %s", index_name, exc)
        return False


def ensure_index(index_name: str) -> None:
    """Create the index with the SupportOps mapping when it does not exist."""
    es = get_es()
    if not es.indices.exists(index=index_name):
        es.indices.create(
            index=index_name,
            settings=SUPPORTOPS_INDEX_BODY["settings"],
            mappings=SUPPORTOPS_INDEX_BODY["mappings"],
        )
        logger.info("Created Elasticsearch index %s", index_name)


def bulk_insert(index_name: str, documents: List[Dict[str, Any]]) -> List[Any]:
    """Insert documents (each carrying an ``id``); returns per-item errors."""
    if not documents:
        return []
    actions = [
        {"_index": index_name, "_id": doc.get("id"), "_source": {k: v for k, v in doc.items() if k != "id"}}
        for doc in documents
    ]
    _, errors = helpers.bulk(get_es(), actions, raise_on_error=False, stats_only=False)
    if errors:
        logger.warning("Bulk insert into %s reported %d errors", index_name, len(errors))
    return list(errors or [])


def refresh(index_name: str) -> None:
    try:
        get_es().indices.refresh(index=index_name)
    except Exception as exc:
        logger.debug("Refresh %s failed: %s", index_name, exc)


def count_documents(index_name: str) -> int:
    try:
        es = get_es()
        if not es.indices.exists(index=index_name):
            return 0
        es.indices.refresh(index=index_name)
        return int(es.count(index=index_name).get("count", 0))
    except Exception as exc:
        logger.warning("Count on %s failed: %s", index_name, exc)
        return 0
