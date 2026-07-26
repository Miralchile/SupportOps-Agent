import os

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Security, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi_jwt import JwtAuthorizationCredentials
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models.agent_trace import AgentTrace
from models.ticket import Ticket
from models.dataset_import_job import DatasetImportJob
from schemas.supportops import (
    AgentTraceResponse,
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    ApiKeyUpdate,
    HumanReviewDecision,
    DatasetImportJobResponse,
    MetricsResponse,
    SupportChatRequest,
    TicketResponse,
    TicketsListResponse,
    TicketUpdateRequest,
    TicketUpdateResult,
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
from service.supportops.data_ingestion import ingest_dataset_content, ingest_ticket_csv, upload_support_docs
from service.supportops.data_quality import revised_ticket_fields
from service.supportops.similar_ticket_search import reindex_ticket
from service.supportops.dataset_adapters import get_dataset_adapter, supported_datasets
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
MAX_DATASET_UPLOAD_BYTES = 512 * 1024 * 1024

# 随仓库内置、可一键导入的数据集（挂载在容器 /datasets 下）
BUNDLED_DATASET_DIR = os.getenv("BUNDLED_DATA_DIR", "/datasets/external")
BUNDLED_DATASET_FILES = {
    "tweetsumm": [
        "tweetsumm/final_train_tweetsum.jsonl",
        "tweetsumm/final_valid_tweetsum.jsonl",
        "tweetsumm/final_test_tweetsum.jsonl",
    ],
}


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


@router.get("/datasets")
async def list_supported_datasets(
    credentials: JwtAuthorizationCredentials = Security(access_security),
):
    _current_user_id(credentials)
    return {"datasets": supported_datasets()}


@router.post("/datasets/import")
async def import_dataset(
    dataset: str = Query(..., description="supportops_csv 或 tweetsumm"),
    file: UploadFile = File(...),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    try:
        get_dataset_adapter(dataset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = await file.read(MAX_DATASET_UPLOAD_BYTES + 1)
    if len(content) > MAX_DATASET_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="数据集文件不能超过 512 MB")
    with use_api_key_config(get_active_api_key_config(db, user_id)):
        result = ingest_dataset_content(
            db,
            user_id,
            dataset,
            file.filename or f"{dataset}.data",
            content,
        )
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/datasets/import_bundled")
async def import_bundled_dataset(
    dataset: str = Query(..., description="内置数据集名，目前支持 tweetsumm"),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    """导入随仓库内置的数据集文件，免手动选择文件。

    重复导入依靠批次校验和与内容哈希去重，天然幂等。
    """
    user_id = _current_user_id(credentials)
    relative_files = BUNDLED_DATASET_FILES.get(dataset.strip().lower())
    if not relative_files:
        raise HTTPException(status_code=404, detail="该数据集没有内置数据文件")

    results = []
    inserted_total = 0
    with use_api_key_config(get_active_api_key_config(db, user_id)):
        for relative_path in relative_files:
            path = os.path.join(BUNDLED_DATASET_DIR, relative_path)
            file_name = os.path.basename(relative_path)
            if not os.path.exists(path):
                results.append({"file": file_name, "status": "missing", "message": "内置数据文件缺失", "inserted": 0})
                continue
            with open(path, "rb") as handle:
                content = handle.read()
            result = ingest_dataset_content(db, user_id, dataset, file_name, content)
            inserted = int(result.get("inserted") or 0)
            inserted_total += inserted
            results.append({
                "file": file_name,
                "status": result.get("status"),
                "message": result.get("message"),
                "inserted": inserted,
            })
    return {
        "dataset": dataset,
        "inserted": inserted_total,
        "results": results,
        "message": f"{dataset} 内置导入完成：新增 {inserted_total} 条工单",
    }


@router.get("/dataset_imports", response_model=list[DatasetImportJobResponse])
async def list_dataset_imports(
    limit: int = Query(20, ge=1, le=100),
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(credentials)
    jobs = (
        db.query(DatasetImportJob)
        .filter(DatasetImportJob.user_id == user_id)
        .order_by(DatasetImportJob.created_at.desc(), DatasetImportJob.id.desc())
        .limit(limit)
        .all()
    )
    return [DatasetImportJobResponse.model_validate(job) for job in jobs]


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


@router.get("/messages/{session_id}")
async def get_session_messages(
    session_id: str,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    """会话消息记录（用户侧客户窗口在人工审核完成后拉取最终答复）。"""
    user_id = _current_user_id(credentials)
    session_key = normalize_session_id(session_id)
    rows = db.execute(
        text(
            """
            SELECT m.user_question, m.model_answer, m.created_at
            FROM messages m
            JOIN sessions s ON s.session_id = m.session_id
            WHERE m.session_id = :session_id AND s.user_id = :user_id
            ORDER BY m.created_at ASC
            """
        ),
        {"session_id": session_key, "user_id": user_id},
    ).fetchall()
    return {
        "session_id": session_key,
        "messages": [
            {"user_question": row[0], "model_answer": row[1], "created_at": str(row[2])}
            for row in rows
        ],
    }


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
        tickets=[TicketResponse.model_validate(ticket) for ticket in tickets],
        total=total,
    )


@router.put("/tickets/{ticket_id}", response_model=TicketUpdateResult)
async def update_ticket(
    ticket_id: int,
    payload: TicketUpdateRequest,
    credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    """编辑工单的问题/处理方式。

    文本走与导入相同的清洗、脱敏和质量重算，随后删除旧检索文档并重建
    embedding 索引，保证列表展示与 agent 检索到的内容一致。
    """
    user_id = _current_user_id(credentials)
    ticket = db.query(Ticket).filter(Ticket.user_id == user_id, Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    try:
        fields = revised_ticket_fields(payload.instruction, payload.response)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    for key, value in fields.items():
        setattr(ticket, key, value)
    db.commit()
    db.refresh(ticket)

    with use_api_key_config(get_active_api_key_config(db, user_id)):
        index_result = reindex_ticket(user_id, ticket)
    warnings = [str(error) for error in (index_result.get("errors") or [])[:5]]
    if index_result.get("stale_docs_removed", 0) < 0:
        warnings.append("旧检索文档清理失败，旧文本可能仍参与相似工单匹配")
    return TicketUpdateResult(
        ticket=TicketResponse.model_validate(ticket),
        indexed=int(index_result.get("indexed") or 0),
        stale_docs_removed=max(0, int(index_result.get("stale_docs_removed") or 0)),
        warnings=warnings,
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
    return [AgentTraceResponse.model_validate(trace) for trace in traces]


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
