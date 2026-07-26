"""SupportOps agent entrypoints: SSE streaming, resume, review lookup, traces.

The LangGraph graph itself lives in ``service.supportops.workflow``; this
module wires it to FastAPI (SSE), the trace table and the chat history.
"""

import os
import uuid
from typing import Any, Callable, Dict, Iterable, List

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from models.agent_trace import AgentTrace
from service.retrieval.es_client import get_es, index_exists
from service.retrieval.search import hybrid_search
from service.supportops.similar_ticket_search import docs_index_name
from service.supportops.tools import chunk_text, compact, json_dumps, simple_similarity, sse_message


def normalize_session_id(session_id: str | None) -> str:
    if not session_id:
        return str(uuid.uuid4()).replace("-", "")[:16]
    cleaned = "".join(ch for ch in session_id if ch.isalnum())
    return (cleaned or str(uuid.uuid4()).replace("-", ""))[:16]


def search_support_docs(user_id: str, question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    index_name = docs_index_name(user_id)

    def fallback_keyword_search() -> List[Dict[str, Any]]:
        """Client-side similarity over all chunks; last resort when the
        Elasticsearch query path fails but the index itself is readable."""
        try:
            if not index_exists(index_name):
                return []
            response = get_es().search(index=index_name, query={"match_all": {}}, size=100)
            ranked = []
            for idx, hit in enumerate(response.get("hits", {}).get("hits", []), start=1):
                source = hit.get("_source", {})
                content = source.get("content_with_weight") or ""
                docnm = source.get("docnm_kwd") or source.get("docnm") or "supportops_doc"
                score = simple_similarity(question, content)
                if content:
                    ranked.append((score, idx, source, content, docnm))
            ranked.sort(key=lambda item: item[0], reverse=True)
            return [
                {
                    "document_id": source.get("doc_id") or hit_order,
                    "document_name": str(docnm).split("/")[-1],
                    "content": content,
                    "score": round(float(score), 4),
                }
                for score, hit_order, source, content, docnm in ranked[:top_k]
            ]
        except Exception:
            return []

    try:
        chunks = hybrid_search(index_name, question, top_k=top_k, vector_weight=0.6)
        sources = [
            {
                "document_id": chunk.get("doc_id") or chunk.get("chunk_id") or str(idx),
                "document_name": str(chunk.get("docnm_kwd") or "supportops_doc").split("/")[-1],
                "content": chunk.get("content_with_weight") or "",
                "score": float(chunk.get("similarity") or 0),
            }
            for idx, chunk in enumerate(chunks, start=1)
        ]
        return sources or fallback_keyword_search()
    except Exception:
        return fallback_keyword_search()


def _record_trace(
    db: Session,
    user_id: str,
    session_id: str,
    trace: Dict[str, Any],
) -> None:
    try:
        db.add(
            AgentTrace(
                user_id=user_id,
                session_id=session_id,
                step_order=trace["step_order"],
                tool_name=trace["tool_name"],
                tool_input=compact(trace.get("tool_input"), 8000),
                tool_output=compact(trace.get("tool_output"), 12000),
                latency_ms=trace["latency_ms"],
                status=trace["status"],
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _write_final_to_history(
    db: Session,
    session_id: str,
    user_id: str,
    question: str,
    final_answer: Dict[str, Any],
    traces: List[Dict[str, Any]],
) -> None:
    try:
        exists = db.execute(
            text("SELECT session_id, user_id FROM sessions WHERE session_id = :session_id"),
            {"session_id": session_id},
        ).fetchone()
        if exists and str(exists[1]) != str(user_id):
            raise PermissionError("Session does not belong to the current user")
        if not exists:
            session_name = question[:40] if question else "SupportOps Agent"
            db.execute(
                text(
                    """
                    INSERT INTO sessions (session_id, user_id, session_name)
                    VALUES (:session_id, :user_id, :session_name)
                    """
                ),
                {"session_id": session_id, "user_id": user_id, "session_name": session_name},
            )

        db.execute(
            text(
                """
                INSERT INTO messages (session_id, user_question, model_answer, documents, recommended_questions, think)
                VALUES (:session_id, :user_question, :model_answer, :documents, :recommended_questions, :think)
                """
            ),
            {
                "session_id": session_id,
                "user_question": question,
                "model_answer": final_answer.get("reply", ""),
                "documents": json_dumps(final_answer.get("sources", [])),
                "recommended_questions": json_dumps([]),
                "think": json_dumps(traces),
            },
        )
        db.commit()
    except Exception:
        db.rollback()


def run_support_agent(db: Session, user_id: str, session_id: str, question: str, api_config: Dict[str, Any] | None = None):
    from service.supportops.workflow import (
        SupportOpsRuntimeContext,
        get_supportops_graph,
        new_turn_state,
    )

    graph = get_supportops_graph()
    config = _graph_config(user_id, session_id)
    snapshot = graph.get_state(config)
    history = [] if snapshot.values else _load_history(db, user_id, session_id)
    runtime = SupportOpsRuntimeContext(
        db_factory=_session_factory(db),
        api_config=api_config,
        max_retries=_max_retries(),
    )
    state = new_turn_state(user_id, session_id, question, history)
    yield from _stream_graph(graph, state, config, runtime)


def resume_support_agent(
    db: Session,
    user_id: str,
    session_id: str,
    decision: Dict[str, Any],
    api_config: Dict[str, Any] | None = None,
) -> Iterable[str]:
    from langgraph.types import Command
    from service.supportops.workflow import SupportOpsRuntimeContext, get_supportops_graph

    graph = get_supportops_graph()
    config = _graph_config(user_id, session_id)
    pending = get_pending_review(user_id, session_id)
    if not pending:
        yield sse_message({"type": "error", "message": "当前会话没有待人工审核的 Agent 执行。"})
        yield "event: end\ndata: [DONE]\n\n"
        return

    runtime = SupportOpsRuntimeContext(
        db_factory=_session_factory(db),
        api_config=api_config,
        max_retries=_max_retries(),
    )
    yield from _stream_graph(graph, Command(resume=decision), config, runtime)


def _max_retries() -> int:
    try:
        return max(0, min(3, int(os.getenv("SUPPORTOPS_MAX_RETRIES", "1"))))
    except ValueError:
        return 1


def get_pending_review(user_id: str, session_id: str) -> Dict[str, Any] | None:
    from service.supportops.workflow import get_supportops_graph

    snapshot = get_supportops_graph().get_state(_graph_config(user_id, session_id))
    if str(snapshot.values.get("user_id") or "") != str(user_id):
        return None
    for task in snapshot.tasks:
        for item in getattr(task, "interrupts", ()):
            value = getattr(item, "value", None)
            if isinstance(value, dict) and value.get("type") == "supportops_human_review":
                return value
    return None


def _graph_config(user_id: str, session_id: str) -> Dict[str, Any]:
    return {
        "configurable": {
            "thread_id": f"{user_id}:{session_id}",
        }
    }


def _session_factory(db: Session) -> Callable[[], Session]:
    return sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False, expire_on_commit=False)


def _load_history(db: Session, user_id: str, session_id: str) -> List[Dict[str, str]]:
    try:
        rows = db.execute(
            text(
                """
                SELECT m.user_question, m.model_answer
                FROM messages m
                JOIN sessions s ON s.session_id = m.session_id
                WHERE m.session_id = :session_id AND s.user_id = :user_id
                ORDER BY m.created_at ASC
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).fetchall()
    except Exception:
        db.rollback()
        return []

    history: List[Dict[str, str]] = []
    for question, answer in rows[-10:]:
        history.append({"role": "user", "content": str(question or "")})
        history.append({"role": "assistant", "content": str(answer or "")})
    return history


def _stream_graph(graph: Any, graph_input: Any, config: Dict[str, Any], runtime: Any) -> Iterable[str]:
    for event in graph.stream(
        graph_input,
        config,
        context=runtime,
        stream_mode="updates",
        durability="sync",
    ):
        if "__interrupt__" in event:
            interrupts = event.get("__interrupt__") or ()
            for item in interrupts:
                approval = getattr(item, "value", item)
                if isinstance(approval, dict):
                    yield sse_message({"type": "human_approval_required", "approval": approval})
            continue

        for _, update in event.items():
            if not isinstance(update, dict):
                continue
            for trace in update.get("trace_events", []):
                payload: Dict[str, Any] = {"type": "trace", "trace": trace}
                for field in ("classification", "sources", "similar_tickets", "escalation", "generated_response", "reflection"):
                    if field in update:
                        payload[field] = update[field]
                yield sse_message(payload)

            final_answer = update.get("final_answer")
            if isinstance(final_answer, dict):
                for piece in chunk_text(final_answer.get("reply", "")):
                    yield sse_message({"type": "reply_delta", "content": piece})
                yield sse_message({"type": "final", "final": final_answer})

    yield "event: end\ndata: [DONE]\n\n"
