"""Validation models for LangGraph node outputs."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    category: str = "general"
    intent: str = "general_inquiry"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


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
