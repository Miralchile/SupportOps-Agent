"""Ticket indexing and similar-ticket retrieval on Elasticsearch."""

import datetime
import hashlib
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from models.ticket import Ticket
from service.retrieval.embedding import embedding_vector_field, generate_embedding
from service.retrieval.es_client import bulk_insert, ensure_index
from service.retrieval.search import hybrid_search
from service.retrieval.text_utils import fine_grained_tokenize, tokenize
from service.supportops.tools import simple_similarity


def ticket_index_name(user_id: str) -> str:
    return f"supportops_tickets_{user_id}"


def docs_index_name(user_id: str) -> str:
    return f"supportops_docs_{user_id}"


def ensure_supportops_index(index_name: str) -> None:
    try:
        ensure_index(index_name)
    except Exception:
        # Index creation is best-effort; bulk insert may still auto-create one.
        return


def _ticket_text(ticket: Ticket) -> str:
    return f"用户问题：{ticket.instruction}\n标准回复：{ticket.response}"


def _build_ticket_documents(
    tickets: Iterable[Ticket],
    index_name: str,
    include_embeddings: bool = True,
) -> List[Dict[str, Any]]:
    ticket_list = list(tickets)
    texts = [_ticket_text(ticket) for ticket in ticket_list]
    embeddings = generate_embedding(texts) if texts and include_embeddings else [None] * len(texts)
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        embeddings = [None] * len(texts)
    now = datetime.datetime.now()

    documents = []
    for ticket, text, embedding in zip(ticket_list, texts, embeddings):
        doc_id = str(ticket.id)
        doc = {
            "id": hashlib.blake2b(f"{doc_id}{text}{index_name}".encode("utf-8"), digest_size=16).hexdigest(),
            "content_ltks": tokenize(text),
            "content_sm_ltks": fine_grained_tokenize(text),
            "content_with_weight": text,
            "title_tks": tokenize(ticket.instruction[:120]),
            "doc_id": doc_id,
            "docnm": f"ticket_{doc_id}",
            "docnm_kwd": f"ticket_{doc_id}",
            "kb_id": index_name,
            "category_kwd": ticket.category,
            "intent_kwd": ticket.intent,
            "source_kwd": ticket.source,
            "available_int": 1,
            "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "create_timestamp_flt": now.timestamp(),
        }
        if embedding:
            doc[embedding_vector_field()] = embedding
        documents.append(doc)
    return documents


def bulk_index_tickets(
    user_id: str,
    tickets: Iterable[Ticket],
    batch_size: int = 64,
    include_embeddings: bool = True,
) -> Dict[str, Any]:
    index_name = ticket_index_name(user_id)
    ticket_list = list(tickets)
    if not ticket_list:
        return {"indexed": 0, "errors": []}

    ensure_supportops_index(index_name)
    indexed = 0
    errors: List[Any] = []
    step = max(1, batch_size)
    for offset in range(0, len(ticket_list), step):
        batch = ticket_list[offset:offset + step]
        documents = _build_ticket_documents(batch, index_name, include_embeddings=include_embeddings)
        try:
            batch_errors = bulk_insert(index_name, documents)
            indexed += len(documents) - len(batch_errors)
            errors.extend(batch_errors)
        except Exception as exc:
            errors.append({"batch_offset": offset, "error": str(exc)})
    return {"indexed": indexed, "errors": errors}


def _fallback_search(db: Session, user_id: str, question: str, top_k: int) -> List[Dict[str, Any]]:
    tickets = db.query(Ticket).filter(Ticket.user_id == user_id).all()
    ranked = []
    for ticket in tickets:
        score = max(
            simple_similarity(question, ticket.instruction),
            simple_similarity(question, ticket.response) * 0.7,
        )
        if score <= 0:
            continue
        ranked.append((score, ticket))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": ticket.id,
            "instruction": ticket.instruction,
            "category": ticket.category,
            "intent": ticket.intent,
            "response": ticket.response,
            "score": round(score, 4),
        }
        for score, ticket in ranked[:top_k]
    ]


def search_similar_tickets(db: Session, user_id: str, question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    try:
        chunks = hybrid_search(ticket_index_name(user_id), question, top_k=top_k)
        ticket_ids: List[int] = []
        scores: Dict[int, float] = {}
        for chunk in chunks:
            try:
                ticket_id = int(chunk.get("doc_id"))
            except (TypeError, ValueError):
                continue
            if ticket_id not in scores:
                ticket_ids.append(ticket_id)
            scores[ticket_id] = max(scores.get(ticket_id, 0.0), float(chunk.get("similarity") or 0.0))

        if not ticket_ids:
            return _fallback_search(db, user_id, question, top_k)

        tickets = db.query(Ticket).filter(Ticket.user_id == user_id, Ticket.id.in_(ticket_ids)).all()
        ticket_by_id = {ticket.id: ticket for ticket in tickets}
        ordered = []
        for ticket_id in ticket_ids:
            ticket = ticket_by_id.get(ticket_id)
            if not ticket:
                continue
            ordered.append(
                {
                    "id": ticket.id,
                    "instruction": ticket.instruction,
                    "category": ticket.category,
                    "intent": ticket.intent,
                    "response": ticket.response,
                    "score": round(scores.get(ticket.id, 0.0), 4),
                }
            )
        return ordered[:top_k] or _fallback_search(db, user_id, question, top_k)
    except Exception:
        return _fallback_search(db, user_id, question, top_k)
