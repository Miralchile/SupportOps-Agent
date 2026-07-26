"""Document file -> text chunks -> Elasticsearch pipeline (doc uploads)."""

from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any, Dict, List, Optional

from service.retrieval.doc_parser import chunk_text, extract_text
from service.retrieval.embedding import embedding_vector_field, generate_embedding
from service.retrieval.es_client import bulk_insert, ensure_index, refresh
from service.retrieval.text_utils import fine_grained_tokenize, tokenize

logger = logging.getLogger("supportops.indexer")


def chunk_doc_id(file_name: str) -> str:
    return hashlib.blake2b(file_name.encode("utf-8"), digest_size=16).hexdigest()


def build_chunk_document(
    chunk: str,
    file_name: str,
    index_name: str,
    embedding: Optional[List[float]] = None,
) -> Dict[str, Any]:
    now = datetime.datetime.now()
    title = file_name.rsplit(".", 1)[0]
    doc: Dict[str, Any] = {
        "id": hashlib.blake2b(f"{chunk}{index_name}".encode("utf-8"), digest_size=16).hexdigest(),
        "content_ltks": tokenize(chunk),
        "content_sm_ltks": fine_grained_tokenize(chunk),
        "content_with_weight": chunk,
        "title_tks": tokenize(title),
        "doc_id": chunk_doc_id(file_name),
        "docnm": file_name,
        "docnm_kwd": file_name,
        "kb_id": index_name,
        "available_int": 1,
        "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "create_timestamp_flt": now.timestamp(),
    }
    if embedding:
        doc[embedding_vector_field()] = embedding
    return doc


def index_file(file_path: str, file_name: str, index_name: str) -> Dict[str, Any]:
    """Parse, chunk, (optionally) embed and index one uploaded document."""
    result = {"status": "failed", "parsed": 0, "processed": 0, "indexed": 0, "errors": []}

    try:
        text = extract_text(file_path)
    except Exception as exc:
        result["errors"].append(str(exc))
        return result

    chunks = chunk_text(text)
    result["parsed"] = len(chunks)
    if not chunks:
        result["errors"].append(f"{file_name}: 未解析出有效文本（扫描版 PDF 需先做 OCR）")
        return result

    embeddings = generate_embedding(chunks)
    if not isinstance(embeddings, list) or len(embeddings) != len(chunks):
        embeddings = [None] * len(chunks)

    documents = [
        build_chunk_document(chunk, file_name, index_name, embedding)
        for chunk, embedding in zip(chunks, embeddings)
    ]
    result["processed"] = len(documents)

    try:
        ensure_index(index_name)
        errors = bulk_insert(index_name, documents)
        refresh(index_name)
    except Exception as exc:
        result["errors"].append(str(exc))
        return result

    result["indexed"] = len(documents) - len(errors)
    result["errors"].extend([str(error) for error in errors[:20]])
    result["status"] = "success" if not errors else "partial_success" if result["indexed"] else "failed"
    logger.info("Indexed %s: %d/%d chunks into %s", file_name, result["indexed"], len(documents), index_name)
    return result
