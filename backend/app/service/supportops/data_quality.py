"""Deterministic cleaning and quality controls for imported support data."""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any, Dict, Tuple

from service.supportops.tools import normalize_label, normalize_question, normalize_text


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_PII_PATTERNS = (
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I), "[EMAIL]"),
    ("payment_card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"), "[PAYMENT_CARD]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{6,}\d)(?!\d)"), "[PHONE]"),
    ("ip", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), "[IP_ADDRESS]"),
)


def clean_markup(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return normalize_text(_SPACE_RE.sub(" ", text))


def redact_pii(value: Any) -> Tuple[str, Dict[str, int]]:
    text = clean_markup(value)
    counts: Dict[str, int] = {}
    for label, pattern, replacement in _PII_PATTERNS:
        text, count = pattern.subn(replacement, text)
        if count:
            counts[label] = count
    return text, counts


def detect_language(*values: str) -> str:
    text = " ".join(values)
    if not text:
        return "unknown"
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk and cjk >= latin * 0.15:
        return "zh"
    if latin:
        return "en"
    return "unknown"


def deterministic_split(conversation_id: str, train: int = 80, validation: int = 10) -> str:
    bucket = int(hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < train:
        return "train"
    if bucket < train + validation:
        return "validation"
    return "test"


def ticket_content_hash(instruction: str, response: str) -> str:
    canonical = f"{normalize_question(instruction)}\n{normalize_question(response)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def quality_score(instruction: str, response: str, has_selected_answer: bool = True) -> float:
    score = 1.0
    question_length = len(instruction.split())
    response_length = len(response.split())
    if question_length < 4:
        score -= 0.2
    if response_length < 6:
        score -= 0.3
    if len(instruction) > 8000 or len(response) > 16000:
        score -= 0.15
    if not has_selected_answer:
        score -= 0.15
    return round(max(0.0, min(score, 1.0)), 3)


def canonical_record(
    *,
    instruction: Any,
    response: Any,
    category: Any,
    intent: Any,
    source: str,
    source_type: str,
    external_id: str | None = None,
    conversation_id: str | None = None,
    raw_category: str | None = None,
    metadata: Dict[str, Any] | None = None,
    has_selected_answer: bool = True,
) -> Dict[str, Any] | None:
    clean_instruction, question_pii = redact_pii(instruction)
    clean_response, response_pii = redact_pii(response)
    if not clean_instruction or not clean_response:
        return None

    pii_counts = dict(question_pii)
    for key, count in response_pii.items():
        pii_counts[key] = pii_counts.get(key, 0) + count
    conversation_key = str(conversation_id or external_id or ticket_content_hash(clean_instruction, clean_response))
    record_metadata = dict(metadata or {})
    if pii_counts:
        record_metadata["pii_redaction_counts"] = pii_counts

    return {
        "instruction": clean_instruction,
        "category": normalize_label(category, default="general"),
        "intent": normalize_label(intent, default="general_inquiry"),
        "response": clean_response,
        "source": source,
        "source_type": source_type,
        "external_id": str(external_id) if external_id is not None else None,
        "conversation_id": conversation_key,
        "language": detect_language(clean_instruction, clean_response),
        "dataset_split": deterministic_split(conversation_key),
        "raw_category": clean_markup(raw_category) if raw_category else None,
        "metadata_json": record_metadata,
        "pii_redacted": bool(pii_counts),
        "quality_score": quality_score(clean_instruction, clean_response, has_selected_answer),
        "content_hash": ticket_content_hash(clean_instruction, clean_response),
    }
