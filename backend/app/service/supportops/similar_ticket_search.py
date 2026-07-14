import datetime
from typing import Any, Dict, Iterable, List

import xxhash
from sqlalchemy.orm import Session

from models.ticket import Ticket
from service.core.rag.nlp import rag_tokenizer
from service.core.rag.nlp.model import generate_embedding
from service.core.rag.nlp.search_v2 import Dealer
from service.core.rag.utils.es_conn import ESConnection
from service.supportops.tools import simple_similarity


def ticket_index_name(user_id: str) -> str:
    return f"supportops_tickets_{user_id}"


def docs_index_name(user_id: str) -> str:
    return f"supportops_docs_{user_id}"


def ensure_supportops_index(index_name: str) -> None:
    try:
        es_connection = ESConnection()
        if not es_connection.es.indices.exists(index=index_name):
            es_connection.es.indices.create(index=index_name, body=es_connection.mapping)
    except Exception:
        # Index creation is best-effort; bulk insert may still auto-create an index.
        return


def _ticket_text(ticket: Ticket) -> str:
    return f"用户问题：{ticket.instruction}\n标准回复：{ticket.response}"


def _build_ticket_documents(tickets: Iterable[Ticket], index_name: str) -> List[Dict[str, Any]]:
    ticket_list = list(tickets)
    texts = [_ticket_text(ticket) for ticket in ticket_list]
    embeddings = generate_embedding(texts) if texts else []
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        embeddings = [None] * len(texts)
    now = str(datetime.datetime.now()).replace("T", " ")[:19]

    documents = []
    for ticket, text, embedding in zip(ticket_list, texts, embeddings):
        doc_id = str(ticket.id)
        chunk_id = xxhash.xxh64((doc_id + text + index_name).encode("utf-8")).hexdigest()
        content_ltks = rag_tokenizer.tokenize(text)
        doc = {
            "id": chunk_id,
            "content_ltks": content_ltks,
            "content_sm_ltks": rag_tokenizer.fine_grained_tokenize(content_ltks),
            "content_with_weight": text,
            "important_kwd": [],
            "important_tks": [],
            "question_kwd": [],
            "question_tks": [],
            "create_time": now,
            "create_timestamp_flt": datetime.datetime.now().timestamp(),
            "available_int": 1,
            "kb_id": index_name,
            "doc_id": doc_id,
            "docnm": f"ticket_{doc_id}",
            "docnm_kwd": f"ticket_{doc_id}",
            "title_tks": rag_tokenizer.tokenize(ticket.instruction[:120]),
            "category_kwd": ticket.category,
            "intent_kwd": ticket.intent,
            "source_kwd": ticket.source,
        }
        if embedding:
            doc[f"q_{len(embedding)}_vec"] = embedding
        documents.append(doc)
    return documents


def bulk_index_tickets(user_id: str, tickets: Iterable[Ticket]) -> Dict[str, Any]:
    index_name = ticket_index_name(user_id)
    ticket_list = list(tickets)
    if not ticket_list:
        return {"indexed": 0, "errors": []}

    ensure_supportops_index(index_name)
    documents = _build_ticket_documents(ticket_list, index_name)
    try:
        errors = ESConnection().insert(documents=documents, indexName=index_name)
        return {"indexed": len(documents) - len(errors), "errors": errors}
    except Exception as exc:
        return {"indexed": 0, "errors": [str(exc)]}


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
    index_name = ticket_index_name(user_id)
    try:
        dealer = Dealer(dataStore=ESConnection())
        results = dealer.retrieval(
            question=question,
            embd_mdl=None,
            tenant_ids=index_name,
            kb_ids=None,
            vector_similarity_weight=0.6,
            page=1,
            page_size=top_k,
        )
        chunks = results.get("chunks", [])
        ticket_ids = []
        scores = {}
        for chunk in chunks:
            doc_id = chunk.get("doc_id")
            if not doc_id:
                continue
            try:
                ticket_id = int(doc_id)
            except (TypeError, ValueError):
                continue
            ticket_ids.append(ticket_id)
            scores[ticket_id] = float(chunk.get("similarity") or chunk.get("vector_similarity") or 0)

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
