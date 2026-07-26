"""Adapters that normalize external support datasets into SupportOps tickets."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from service.supportops.data_quality import canonical_record, clean_markup
from service.supportops.ticket_cleaner import decode_csv


@dataclass(frozen=True)
class AdaptedDataset:
    dataset_name: str
    dataset_version: str
    source_type: str
    records: List[Dict[str, Any]]
    rejected: int
    errors: List[str]


class DatasetAdapter:
    dataset_name = "unknown"
    dataset_version = "unknown"
    source_type = "unknown"

    def adapt(self, content: bytes, filename: str, limit: int | None = None) -> AdaptedDataset:
        raise NotImplementedError

    def result(self, records: List[Dict[str, Any]], rejected: int, errors: List[str]) -> AdaptedDataset:
        return AdaptedDataset(
            dataset_name=self.dataset_name,
            dataset_version=self.dataset_version,
            source_type=self.source_type,
            records=records,
            rejected=rejected,
            errors=errors[:100],
        )


class SupportOpsCsvAdapter(DatasetAdapter):
    dataset_name = "supportops_csv"
    dataset_version = "1"
    source_type = "user_provided"

    aliases = {
        "instruction": ("instruction", "question", "query", "customer_message"),
        "category": ("category", "topic"),
        "intent": ("intent", "label"),
        "response": ("response", "answer", "agent_response"),
        "external_id": ("external_id", "ticket_id", "id"),
        "conversation_id": ("conversation_id", "dialog_id", "thread_id"),
    }

    def _column(self, row: Dict[str, Any], name: str) -> Any:
        lowered = {str(key).strip().lower(): value for key, value in row.items() if key}
        return next((lowered[key] for key in self.aliases[name] if key in lowered), None)

    def adapt(self, content: bytes, filename: str, limit: int | None = None) -> AdaptedDataset:
        reader = csv.DictReader(io.StringIO(decode_csv(content)))
        records: List[Dict[str, Any]] = []
        errors: List[str] = []
        rejected = 0
        for line_no, row in enumerate(reader, start=2):
            if limit is not None and len(records) >= limit:
                break
            record = canonical_record(
                instruction=self._column(row, "instruction"),
                response=self._column(row, "response"),
                category=self._column(row, "category"),
                intent=self._column(row, "intent"),
                source=filename or "csv",
                source_type=self.source_type,
                external_id=self._column(row, "external_id"),
                conversation_id=self._column(row, "conversation_id"),
                metadata={"source_line": line_no},
            )
            if record is None:
                rejected += 1
                errors.append(f"第 {line_no} 行缺少有效问题或回复")
                continue
            records.append(record)
        return self.result(records, rejected, errors)


class MSDialogAdapter(DatasetAdapter):
    dataset_name = "msdialog"
    dataset_version = "complete"
    source_type = "real_anonymized"

    @staticmethod
    def _dialogs(payload: Any) -> Iterable[tuple[str, Dict[str, Any]]]:
        if isinstance(payload, dict):
            for dialog_id, dialog in payload.items():
                if isinstance(dialog, dict):
                    yield str(dialog_id), dialog
        elif isinstance(payload, list):
            for index, dialog in enumerate(payload):
                if isinstance(dialog, dict):
                    yield str(dialog.get("dialog_id") or index), dialog

    def adapt(self, content: bytes, filename: str, limit: int | None = None) -> AdaptedDataset:
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self.result([], 1, [f"MSDialog JSON 解析失败: {exc}"])

        records: List[Dict[str, Any]] = []
        errors: List[str] = []
        rejected = 0
        for dialog_id, dialog in self._dialogs(payload):
            if limit is not None and len(records) >= limit:
                break
            utterances = sorted(
                [item for item in dialog.get("utterances", []) if isinstance(item, dict)],
                key=lambda item: int(item.get("utterance_pos") or 0),
            )
            user_turns = [item for item in utterances if str(item.get("actor_type", "")).lower() == "user"]
            agent_turns = [item for item in utterances if str(item.get("actor_type", "")).lower() == "agent"]
            selected = next((item for item in agent_turns if str(item.get("is_answer", "0")).lower() in {"1", "true"}), None)
            answer = selected or (agent_turns[0] if agent_turns else None)
            if not user_turns or not answer:
                rejected += 1
                errors.append(f"dialog {dialog_id}: 缺少用户问题或客服回复")
                continue

            raw_category = clean_markup(dialog.get("category") or "technical")
            tags = clean_markup(user_turns[0].get("tags") or "").split()
            record = canonical_record(
                instruction=user_turns[0].get("utterance"),
                response=answer.get("utterance"),
                category=raw_category or "technical",
                intent=f"{raw_category or 'technical'}_support",
                source="msdialog",
                source_type=self.source_type,
                external_id=dialog_id,
                conversation_id=dialog_id,
                raw_category=raw_category,
                has_selected_answer=selected is not None,
                metadata={
                    "dataset": "MSDialog",
                    "dialog_time": dialog.get("dialog_time"),
                    "title": clean_markup(dialog.get("title")),
                    "turn_count": len(utterances),
                    "question_dialog_acts": tags,
                    "answer_affiliation": clean_markup(answer.get("affiliation")),
                    "answer_vote": answer.get("vote"),
                    "selected_answer": selected is not None,
                },
            )
            if record is None:
                rejected += 1
                errors.append(f"dialog {dialog_id}: 清洗后问题或回复为空")
                continue
            records.append(record)
        return self.result(records, rejected, errors)


class TweetSummAdapter(DatasetAdapter):
    dataset_name = "tweetsumm"
    dataset_version = "emnlp-2021"
    source_type = "real_derived"

    def adapt(self, content: bytes, filename: str, limit: int | None = None) -> AdaptedDataset:
        records: List[Dict[str, Any]] = []
        errors: List[str] = []
        rejected = 0
        lowered_filename = filename.lower()
        source_split = "validation" if "valid" in lowered_filename else "test" if "test" in lowered_filename else "train"
        for line_no, raw_line in enumerate(content.decode("utf-8-sig").splitlines(), start=1):
            if limit is not None and len(records) >= limit:
                break
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                rejected += 1
                errors.append(f"第 {line_no} 行 JSONL 解析失败: {exc}")
                continue
            annotations = item.get("annotations") or []
            summary = next(
                (annotation.get("abstractive") for annotation in annotations if len(annotation.get("abstractive") or []) >= 2),
                None,
            )
            if not summary:
                rejected += 1
                errors.append(f"第 {line_no} 行缺少客户与客服的成对摘要")
                continue
            conversation_id = str(item.get("conversation_id") or f"{source_split}-{line_no}")
            record = canonical_record(
                instruction=summary[0],
                response=summary[1],
                category="customer_support",
                intent="case_resolution",
                source="tweetsumm",
                source_type=self.source_type,
                external_id=conversation_id,
                conversation_id=conversation_id,
                metadata={
                    "dataset": "TweetSumm",
                    "derived_from_real_dialog": True,
                    "annotation_count": len(annotations),
                    "license": "CDLA-Sharing-1.0",
                    "original_split": source_split,
                    "raw_dialog_included": False,
                },
            )
            if record is None:
                rejected += 1
                continue
            record["dataset_split"] = source_split
            records.append(record)
        return self.result(records, rejected, errors)


_ADAPTERS = {
    "supportops_csv": SupportOpsCsvAdapter,
    "msdialog": MSDialogAdapter,
    "tweetsumm": TweetSummAdapter,
}


def get_dataset_adapter(name: str) -> DatasetAdapter:
    key = name.strip().lower()
    adapter = _ADAPTERS.get(key)
    if not adapter:
        raise ValueError(f"不支持的数据集类型: {name}; 可选值: {', '.join(sorted(_ADAPTERS))}")
    return adapter()


def supported_datasets() -> List[Dict[str, str]]:
    unique = {
        adapter.dataset_name: adapter
        for adapter in (SupportOpsCsvAdapter, MSDialogAdapter, TweetSummAdapter)
    }
    return [
        {
            "name": adapter.dataset_name,
            "version": adapter.dataset_version,
            "source_type": adapter.source_type,
        }
        for adapter in unique.values()
    ]
