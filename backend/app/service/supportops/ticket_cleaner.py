import csv
import io
from typing import Any, Dict, List, Tuple

from service.supportops.tools import normalize_label, normalize_question, normalize_text


REQUIRED_FIELDS = ["instruction", "category", "intent", "response"]


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _field_map(fieldnames: List[str]) -> Dict[str, str]:
    aliases = {field.lower().strip(): field for field in fieldnames if field}
    return {field: aliases.get(field) for field in REQUIRED_FIELDS}


def validate_csv_fields(fieldnames: List[str]) -> Tuple[bool, List[str], Dict[str, str]]:
    mapping = _field_map(fieldnames)
    missing = [field for field, original in mapping.items() if not original]
    return len(missing) == 0, missing, mapping


def clean_ticket_rows(content: bytes, source: str = "csv") -> Dict[str, Any]:
    text = decode_csv(content)
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    valid, missing, mapping = validate_csv_fields(fieldnames)
    if not valid:
        return {
            "rows": [],
            "errors": [f"CSV 缺少必需字段: {', '.join(missing)}"],
            "skipped": 0,
            "duplicates_in_file": 0,
        }

    rows = []
    errors = []
    seen_questions = set()
    skipped = 0
    duplicates = 0

    for line_no, raw in enumerate(reader, start=2):
        instruction = normalize_text(raw.get(mapping["instruction"]))
        category = normalize_label(raw.get(mapping["category"]))
        intent = normalize_label(raw.get(mapping["intent"]), default="general_inquiry")
        response = normalize_text(raw.get(mapping["response"]))

        if not instruction or not response:
            skipped += 1
            errors.append(f"第 {line_no} 行 instruction/response 为空，已跳过")
            continue

        question_key = normalize_question(instruction)
        if question_key in seen_questions:
            duplicates += 1
            continue
        seen_questions.add(question_key)

        rows.append(
            {
                "instruction": instruction,
                "category": category,
                "intent": intent,
                "response": response,
                "source": source,
            }
        )

    return {
        "rows": rows,
        "errors": errors,
        "skipped": skipped,
        "duplicates_in_file": duplicates,
    }
