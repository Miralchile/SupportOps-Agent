from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SupportChatRequest(BaseModel):
    message: str


class HumanReviewDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_reply: Optional[str] = None
    reviewer_note: Optional[str] = None


class TicketResponse(BaseModel):
    id: int
    instruction: str
    category: str
    intent: str
    response: str
    source: str
    source_type: str
    external_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language: str
    dataset_split: str
    pii_redacted: bool
    quality_score: float
    import_job_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketUpdateRequest(BaseModel):
    instruction: str
    response: str


class TicketUpdateResult(BaseModel):
    ticket: TicketResponse
    indexed: int
    stale_docs_removed: int
    warnings: List[str] = []


class AgentTraceResponse(BaseModel):
    id: int
    session_id: str
    step_order: int
    tool_name: str
    tool_input: Optional[str]
    tool_output: Optional[str]
    latency_ms: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketsListResponse(BaseModel):
    tickets: List[TicketResponse]
    total: int


class DatasetImportJobResponse(BaseModel):
    id: int
    dataset_name: str
    dataset_version: str
    source_filename: str
    source_type: str
    status: str
    checksum: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    pii_redacted_rows: int
    indexed_rows: int
    split_counts: Dict[str, int]
    import_options: Dict[str, Any]
    errors: List[Any]
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MetricsResponse(BaseModel):
    ticket_total: int
    category_distribution: Dict[str, int]
    intent_distribution: Dict[str, int]
    risk_level_distribution: Dict[str, int]
    high_risk_ratio: float
    human_transfer_ratio: float
    top_intents: List[Dict[str, Any]]


class ApiKeyCreate(BaseModel):
    name: str = "DashScope"
    provider: str = "dashscope"
    api_key: str
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v3"
    is_active: bool = True


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    embedding_model: Optional[str] = None
    is_active: Optional[bool] = None


class ApiKeyTestRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v3"


class ApiKeyTestResponse(BaseModel):
    status: str
    chat_ok: bool
    embedding_ok: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    provider: str
    masked_api_key: str
    base_url: str
    model: str
    embedding_model: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
