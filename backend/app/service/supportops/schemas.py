from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    category: str = "general"
    intent: str = "general_inquiry"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


class SearchSource(BaseModel):
    document_id: str
    document_name: str
    content: str
    score: float = 0.0


class SimilarTicket(BaseModel):
    id: int
    instruction: str
    category: str
    intent: str
    response: str
    score: float = 0.0


class EscalationResult(BaseModel):
    need_human: bool = False
    risk_level: str = "low"
    reason: str = ""
    matched_rules: List[str] = Field(default_factory=list)


class GeneratedResponse(BaseModel):
    reply: str
    summary: str
    next_action: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)


class ReflectionResult(BaseModel):
    missing_knowledge: bool = False
    low_confidence: bool = False
    high_risk: bool = False
    need_follow_up: bool = False
    must_human: bool = False
    reason: str = ""


class AgentTraceStep(BaseModel):
    step_order: int
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Dict[str, Any]
    latency_ms: int
    status: str


class SupportFinalAnswer(BaseModel):
    user_question: str
    category: str
    intent: str
    risk_level: str
    need_human: bool
    reply: str
    similar_tickets: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    agent_trace: List[Dict[str, Any]]
    next_action: str
    summary: Optional[str] = None
    reflection: Optional[Dict[str, Any]] = None
