"""Stateful LangGraph orchestration for the SupportOps Agent."""

from __future__ import annotations

import operator
import threading
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Dict, List, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from service.supportops.api_key_context import use_api_key_config
from service.supportops.checkpointing import get_checkpointer
from service.supportops.escalation_checker import check_escalation
from service.supportops.intent_classifier import classify_intent
from service.supportops.query_rewriter import rewrite_query
from service.supportops.response_generator import generate_response, reflect_response
from service.supportops.schemas import (
    EscalationResult,
    GeneratedResponse,
    IntentClassification,
    ReflectionResult,
)


class SupportOpsState(TypedDict, total=False):
    user_id: str
    session_id: str
    turn_id: str
    question: str
    retrieval_query: str
    messages: Annotated[List[Dict[str, Any]], operator.add]
    classification: Dict[str, Any]
    sources: List[Dict[str, Any]]
    similar_tickets: List[Dict[str, Any]]
    escalation: Dict[str, Any]
    generated_response: Dict[str, Any]
    reflection: Dict[str, Any]
    retry_count: int
    human_decision: Dict[str, Any]
    trace_events: Annotated[List[Dict[str, Any]], operator.add]
    final_answer: Dict[str, Any]


@dataclass
class SupportOpsRuntimeContext:
    db_factory: Callable[[], Session]
    api_config: Dict[str, Any] | None = None
    max_retries: int = 1


def _validated(model: Any, value: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return model.model_validate(value).model_dump()
    except Exception:
        return fallback


def _current_traces(state: SupportOpsState, extra: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    turn_id = state.get("turn_id")
    traces = [item for item in state.get("trace_events", []) if item.get("turn_id") == turn_id]
    if extra and extra.get("turn_id") == turn_id:
        traces.append(extra)
    return sorted(traces, key=lambda item: (item.get("step_order", 0), item.get("attempt", 0)))


def _record_trace(runtime: SupportOpsRuntimeContext, state: SupportOpsState, trace: Dict[str, Any]) -> None:
    # Import lazily to avoid a module cycle while keeping the legacy trace table/API.
    from service.supportops.support_agent import _record_trace as persist_trace

    db = runtime.db_factory()
    try:
        persist_trace(db, state["user_id"], state["session_id"], trace)
    finally:
        db.close()


def _execute(
    state: SupportOpsState,
    runtime: SupportOpsRuntimeContext,
    step_order: int,
    tool_name: str,
    tool_input: Dict[str, Any],
    fn: Callable[[], Any],
) -> tuple[Any, Dict[str, Any]]:
    started = time.perf_counter()
    status = "success"
    try:
        context = use_api_key_config(runtime.api_config) if runtime.api_config else nullcontext()
        with context:
            output = fn()
    except Exception as exc:
        status = "failed"
        output = {"error": str(exc)}

    trace = {
        "turn_id": state["turn_id"],
        "attempt": state.get("retry_count", 0),
        "step_order": step_order,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": output,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": status,
    }
    _record_trace(runtime, state, trace)
    return output, trace


def _planner_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    plan = {
        "graph": "supportops_langgraph_v1",
        "parallel": ["rag_search", "similar_ticket_search"],
        "conditional": ["query_rewrite", "human_review", "finalize"],
        "max_retries": runtime.context.max_retries,
    }
    _, trace = _execute(state, runtime.context, 0, "planner", {"question": state["question"]}, lambda: plan)
    return {"trace_events": [trace]}


def _classify_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    fallback = {
        "category": "general",
        "intent": "general_inquiry",
        "confidence": 0.0,
        "reason": "意图识别失败。",
    }
    output, trace = _execute(
        state,
        runtime.context,
        1,
        "intent_classifier",
        {"question": state["question"], "history_turns": len(state.get("messages", []))},
        lambda: classify_intent(state["question"], [], state.get("messages", [])),
    )
    return {
        "classification": _validated(IntentClassification, output, fallback),
        "trace_events": [trace],
    }


def _rag_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    from service.supportops.support_agent import search_support_docs

    query = state.get("retrieval_query") or state["question"]
    output, trace = _execute(
        state,
        runtime.context,
        2,
        "rag_search",
        {"query": query, "top_k": 5},
        lambda: search_support_docs(state["user_id"], query),
    )
    return {"sources": output if isinstance(output, list) else [], "trace_events": [trace]}


def _similar_tickets_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    from service.supportops.similar_ticket_search import search_similar_tickets

    query = state.get("retrieval_query") or state["question"]

    def search() -> List[Dict[str, Any]]:
        db = runtime.context.db_factory()
        try:
            return search_similar_tickets(db, state["user_id"], query, top_k=5)
        finally:
            db.close()

    output, trace = _execute(
        state,
        runtime.context,
        3,
        "similar_ticket_search",
        {"query": query, "top_k": 5},
        search,
    )
    return {"similar_tickets": output if isinstance(output, list) else [], "trace_events": [trace]}


def _risk_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    fallback = {
        "need_human": True,
        "risk_level": "high",
        "reason": "风险判断失败，按安全策略转人工。",
        "matched_rules": ["risk_check_failed"],
    }
    output, trace = _execute(
        state,
        runtime.context,
        4,
        "escalation_checker",
        {"question": state["question"], "classification": state.get("classification", {})},
        lambda: check_escalation(
            state["question"],
            state.get("classification", {}),
            state.get("sources", []),
            state.get("similar_tickets", []),
            state.get("messages", []),
        ),
    )
    return {"escalation": _validated(EscalationResult, output, fallback), "trace_events": [trace]}


def _generate_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    fallback = {
        "reply": "当前无法可靠生成自动回复，已建议转人工处理。",
        "summary": "回复生成失败。",
        "next_action": "转人工",
        "citations": [],
    }
    output, trace = _execute(
        state,
        runtime.context,
        5,
        "response_generator",
        {
            "question": state["question"],
            "sources_count": len(state.get("sources", [])),
            "similar_tickets_count": len(state.get("similar_tickets", [])),
            "escalation": state.get("escalation", {}),
        },
        lambda: generate_response(
            state["question"],
            state.get("classification", {}),
            state.get("sources", []),
            state.get("similar_tickets", []),
            state.get("escalation", {}),
            state.get("messages", []),
        ),
    )
    return {"generated_response": _validated(GeneratedResponse, output, fallback), "trace_events": [trace]}


def _reflect_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    fallback = {
        "missing_knowledge": True,
        "low_confidence": True,
        "high_risk": bool(state.get("escalation", {}).get("need_human")),
        "need_follow_up": True,
        "must_human": bool(state.get("escalation", {}).get("need_human")),
        "reason": "质量检查失败，采用保守策略。",
    }
    output, trace = _execute(
        state,
        runtime.context,
        6,
        "reflection",
        {"question": state["question"], "draft": state.get("generated_response", {})},
        lambda: reflect_response(
            state["question"],
            state.get("classification", {}),
            state.get("sources", []),
            state.get("similar_tickets", []),
            state.get("escalation", {}),
            state.get("generated_response", {}),
            state.get("messages", []),
        ),
    )
    return {"reflection": _validated(ReflectionResult, output, fallback), "trace_events": [trace]}


def _after_reflection(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Literal["rewrite_query", "human_review", "finalize"]:
    escalation = state.get("escalation", {})
    reflection = state.get("reflection", {})
    if escalation.get("need_human") or reflection.get("must_human"):
        return "human_review"
    if reflection.get("need_follow_up") and state.get("retry_count", 0) < runtime.context.max_retries:
        return "rewrite_query"
    return "finalize"


def _rewrite_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    output, trace = _execute(
        state,
        runtime.context,
        7,
        "query_rewrite",
        {"question": state["question"], "attempt": state.get("retry_count", 0) + 1},
        lambda: rewrite_query(state["question"], state.get("classification", {}), state.get("messages", [])),
    )
    query = output.get("query") if isinstance(output, dict) else state["question"]
    return {
        "retrieval_query": query or state["question"],
        "retry_count": state.get("retry_count", 0) + 1,
        "sources": [],
        "similar_tickets": [],
        "trace_events": [trace],
    }


def _human_review_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    draft = state.get("generated_response", {})
    decision = interrupt(
        {
            "type": "supportops_human_review",
            "session_id": state["session_id"],
            "turn_id": state["turn_id"],
            "question": state["question"],
            "risk_level": state.get("escalation", {}).get("risk_level", "high"),
            "reason": state.get("escalation", {}).get("reason", ""),
            "proposed_reply": draft.get("reply", ""),
            "allowed_actions": ["approve", "edit", "reject"],
        }
    )
    decision = decision if isinstance(decision, dict) else {"action": "reject"}
    action = decision.get("action") if decision.get("action") in {"approve", "edit", "reject"} else "reject"
    edited_reply = str(decision.get("edited_reply") or "").strip()
    response = dict(draft)
    if action == "edit" and edited_reply:
        response["reply"] = edited_reply
        response["next_action"] = "人工修改后回复"
    elif action == "approve":
        response["next_action"] = "人工审核后回复"
    else:
        response["reply"] = edited_reply or "该问题已转交人工客服处理，自动回复暂不发送。"
        response["next_action"] = "转人工"

    output = {"action": action, "reviewer_note": str(decision.get("reviewer_note") or "")}
    _, trace = _execute(state, runtime.context, 8, "human_review", {"risk": state.get("escalation", {})}, lambda: output)
    return {"human_decision": output, "generated_response": response, "trace_events": [trace]}


def _finalize_node(state: SupportOpsState, runtime: Runtime[SupportOpsRuntimeContext]) -> Dict[str, Any]:
    escalation = state.get("escalation", {})
    reflection = state.get("reflection", {})
    generated = state.get("generated_response", {})
    human_decision = state.get("human_decision", {})
    need_human = bool(escalation.get("need_human")) or bool(reflection.get("must_human"))
    next_action = generated.get("next_action") or "自动回复"
    if need_human and not human_decision:
        next_action = "转人工"
    elif reflection.get("need_follow_up") and state.get("retry_count", 0) == 0:
        next_action = "追问用户"

    trace_output = {
        "next_action": next_action,
        "human_reviewed": bool(human_decision),
        "retry_count": state.get("retry_count", 0),
    }
    _, trace = _execute(state, runtime.context, 9, "finalize", {"turn_id": state["turn_id"]}, lambda: trace_output)
    traces = _current_traces(state, trace)
    final_answer = {
        "user_question": state["question"],
        "category": state.get("classification", {}).get("category", "general"),
        "intent": state.get("classification", {}).get("intent", "general_inquiry"),
        "risk_level": escalation.get("risk_level", "low"),
        "need_human": need_human,
        "reply": generated.get("reply", ""),
        "similar_tickets": state.get("similar_tickets", []),
        "sources": state.get("sources", []),
        "agent_trace": traces,
        "next_action": next_action,
        "summary": generated.get("summary", ""),
        "reflection": reflection,
        "human_decision": human_decision or None,
        "retry_count": state.get("retry_count", 0),
        "workflow": "langgraph",
    }

    from service.supportops.support_agent import _write_final_to_history

    db = runtime.context.db_factory()
    try:
        _write_final_to_history(
            db,
            state["session_id"],
            state["user_id"],
            state["question"],
            final_answer,
            traces,
        )
    finally:
        db.close()

    return {
        "final_answer": final_answer,
        "messages": [{"role": "assistant", "content": final_answer["reply"]}],
        "trace_events": [trace],
    }


def build_supportops_graph(checkpointer: Any = None):
    builder = StateGraph(SupportOpsState, context_schema=SupportOpsRuntimeContext)
    builder.add_node("planner", _planner_node)
    builder.add_node("intent_classifier", _classify_node)
    builder.add_node("rag_search", _rag_node)
    builder.add_node("similar_ticket_search", _similar_tickets_node)
    builder.add_node("escalation_checker", _risk_node)
    builder.add_node("response_generator", _generate_node)
    builder.add_node("reflection", _reflect_node)
    builder.add_node("rewrite_query", _rewrite_node)
    builder.add_node("human_review", _human_review_node)
    builder.add_node("finalize", _finalize_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "intent_classifier")
    builder.add_edge("intent_classifier", "rag_search")
    builder.add_edge("intent_classifier", "similar_ticket_search")
    builder.add_edge(["rag_search", "similar_ticket_search"], "escalation_checker")
    builder.add_edge("escalation_checker", "response_generator")
    builder.add_edge("response_generator", "reflection")
    builder.add_conditional_edges("reflection", _after_reflection)
    builder.add_edge("rewrite_query", "rag_search")
    builder.add_edge("rewrite_query", "similar_ticket_search")
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer or get_checkpointer(), name="supportops_agent")


_graph_lock = threading.Lock()
_graph = None


def get_supportops_graph():
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                _graph = build_supportops_graph()
    return _graph


def new_turn_state(
    user_id: str,
    session_id: str,
    question: str,
    history: List[Dict[str, Any]] | None = None,
) -> SupportOpsState:
    return {
        "user_id": user_id,
        "session_id": session_id,
        "turn_id": uuid.uuid4().hex,
        "question": question,
        "retrieval_query": question,
        "messages": [*(history or []), {"role": "user", "content": question}],
        "classification": {},
        "sources": [],
        "similar_tickets": [],
        "escalation": {},
        "generated_response": {},
        "reflection": {},
        "retry_count": 0,
        "human_decision": {},
        "final_answer": {},
    }
