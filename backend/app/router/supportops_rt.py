from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Security, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi_jwt import JwtAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.agent_trace import AgentTrace
from models.ticket import Ticket
from schemas.supportops import (
    AgentTraceResponse,
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    ApiKeyUpdate,
    HumanReviewDecision,
    MetricsResponse,
    SupportChatRequest,
    TicketResponse,
    TicketsListResponse,
)
from service.auth import access_security
from service.supportops.api_key_context import use_api_key_config
from service.supportops.api_key_service import (
    activate_api_key,
    create_api_key,
    delete_api_key,
    get_active_api_key_config,
    list_api_keys,
    test_api_key_payload,
    test_saved_api_key,
    update_api_key,
)
from service.supportops.data_ingestion import ingest_ticket_csv, upload_support_docs
from service.supportops.support_agent import (
    get_pending_review,
    normalize_session_id,
    resume_support_agent,
    run_support_agent,
)
from service.supportops.checkpointing import checkpoint_status
from service.supportops.tools import safe_json_loads
from utils.database import get_db

router = APIRouter(prefix="/supportops", tags=["SupportOps Agent"])


def _current_user_id(credentials: JwtAuthorizationCredentials) -> str:
    user_id = str(credentials.subject.get("user_id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return user_id


@router.post("/upload_tickets")
async def upload_tickets(
    file: UploadFile = File(...),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")
    content = await file.read()
    with use_api_key_config(get_active_api_key_config(db, user_id)):
        result = ingest_ticket_csv(db, user_id, file.filename or "tickets.csv", content)
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/upload_docs")
async def upload_docs(
    session_id: str | None = Query(None),
    files: list[UploadFile] = File(...),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    with use_api_key_config(get_active_api_key_config(db, user_id)):
        result = upload_support_docs(user_id=user_id, files=files, session_id=normalize_session_id(session_id))
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/chat")
async def supportops_chat(
    session_id: str = Query(...),
    request: SupportChatRequest = Body(...),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    session_key = normalize_session_id(session_id)
    question = request.message.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message 不能为空")

    return StreamingResponse(
        run_support_agent(
            db=db,
            user_id=user_id,
            session_id=session_key,
            question=question,
            api_config=get_active_api_key_config(db, user_id),
        ),
        media_type="text/event-stream",
    )


@router.post("/chat/resume")
async def resume_supportops_chat(
    session_id: str = Query(...),
    request: HumanReviewDecision = Body(...),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    session_key = normalize_session_id(session_id)
    return StreamingResponse(
        resume_support_agent(
            db=db,
            user_id=user_id,
            session_id=session_key,
            decision=request.model_dump(),
            api_config=get_active_api_key_config(db, user_id),
        ),
        media_type="text/event-stream",
    )


@router.get("/reviews/{session_id}")
async def pending_human_review(
    session_id: str,
    credentials: JwtAuthorizationCredentials = Security(access_security),
):
    user_id = _current_user_id(credentials)
    review = get_pending_review(user_id, normalize_session_id(session_id))
    return {"pending": bool(review), "review": review}


@router.get("/workflow/status")
async def supportops_workflow_status(
    credentials: JwtAuthorizationCredentials = Security(access_security),
):
    _current_user_id(credentials)
    return {"framework": "langgraph", **checkpoint_status()}


@router.get("/api_keys", response_model=list[ApiKeyResponse])
async def get_api_keys(
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return list_api_keys(db, user_id)


@router.post("/api_keys", response_model=ApiKeyResponse)
async def add_api_key(
    payload: ApiKeyCreate,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return create_api_key(db, user_id, payload)


@router.post("/api_keys/test", response_model=ApiKeyTestResponse)
async def test_api_key(
    payload: ApiKeyTestRequest,
    credentials: JwtAuthorizationCredentials = Security(access_security),
):
    _current_user_id(credentials)
    return test_api_key_payload(payload)


@router.put("/api_keys/{key_id}", response_model=ApiKeyResponse)
async def edit_api_key(
    key_id: int,
    payload: ApiKeyUpdate,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return update_api_key(db, user_id, key_id, payload)


@router.post("/api_keys/{key_id}/activate", response_model=ApiKeyResponse)
async def set_active_api_key(
    key_id: int,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return activate_api_key(db, user_id, key_id)


@router.post("/api_keys/{key_id}/test", response_model=ApiKeyTestResponse)
async def test_existing_api_key(
    key_id: int,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return test_saved_api_key(db, user_id, key_id)


@router.delete("/api_keys/{key_id}")
async def remove_api_key(
    key_id: int,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    return delete_api_key(db, user_id, key_id)


@router.get("/tickets", response_model=TicketsListResponse)
async def get_tickets(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    query = db.query(Ticket).filter(Ticket.user_id == user_id)
    total = query.count()
    tickets = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit).all()
    return TicketsListResponse(
        tickets=[TicketResponse.from_orm(ticket) for ticket in tickets],
        total=total,
    )


@router.get("/traces/{session_id}", response_model=list[AgentTraceResponse])
async def get_traces(
    session_id: str,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    session_key = normalize_session_id(session_id)
    traces = (
        db.query(AgentTrace)
        .filter(AgentTrace.user_id == user_id, AgentTrace.session_id == session_key)
        .order_by(AgentTrace.created_at.asc(), AgentTrace.step_order.asc(), AgentTrace.id.asc())
        .all()
    )
    return [AgentTraceResponse.from_orm(trace) for trace in traces]


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    ticket_total = db.query(Ticket).filter(Ticket.user_id == user_id).count()

    category_distribution = {
        row[0] or "unknown": int(row[1])
        for row in db.query(Ticket.category, func.count(Ticket.id))
        .filter(Ticket.user_id == user_id)
        .group_by(Ticket.category)
        .all()
    }
    intent_distribution = {
        row[0] or "unknown": int(row[1])
        for row in db.query(Ticket.intent, func.count(Ticket.id))
        .filter(Ticket.user_id == user_id)
        .group_by(Ticket.intent)
        .all()
    }

    escalation_outputs = (
        db.query(AgentTrace.tool_output)
        .filter(AgentTrace.user_id == user_id, AgentTrace.tool_name == "escalation_checker")
        .all()
    )
    risk_level_distribution = {"low": 0, "medium": 0, "high": 0}
    human_transfer_count = 0
    for row in escalation_outputs:
        output = safe_json_loads(row[0], {}) or {}
        risk_level = output.get("risk_level", "low")
        if risk_level not in risk_level_distribution:
            risk_level = "low"
        risk_level_distribution[risk_level] += 1
        if output.get("need_human"):
            human_transfer_count += 1

    total_escalations = max(len(escalation_outputs), 1)
    top_intents = [
        {"intent": intent, "count": count}
        for intent, count in sorted(intent_distribution.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    return MetricsResponse(
        ticket_total=ticket_total,
        category_distribution=category_distribution,
        intent_distribution=intent_distribution,
        risk_level_distribution=risk_level_distribution,
        high_risk_ratio=round(risk_level_distribution["high"] / total_escalations, 4),
        human_transfer_ratio=round(human_transfer_count / total_escalations, 4),
        top_intents=top_intents,
    )
