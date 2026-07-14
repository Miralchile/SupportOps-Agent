import os
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.ticket import Ticket
from service.core.api.utils.file_utils import get_project_base_directory
from service.core.file_parse import execute_insert_process
from service.core.rag.utils.es_conn import ESConnection
from service.supportops.similar_ticket_search import (
    bulk_index_tickets,
    docs_index_name,
    ensure_supportops_index,
)
from service.supportops.ticket_cleaner import clean_ticket_rows
from service.supportops.tools import normalize_question


def _count_index_documents(index_name: str) -> int:
    try:
        es = ESConnection().es
        if not es.indices.exists(index=index_name):
            return 0
        es.indices.refresh(index=index_name)
        return int(es.count(index=index_name).get("count", 0))
    except Exception:
        return 0


def ingest_ticket_csv(db: Session, user_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    cleaned = clean_ticket_rows(content, source=filename or "csv")
    rows = cleaned["rows"]
    if not rows:
        return {
            "status": "failed",
            "message": "没有可导入的工单数据",
            "inserted": 0,
            "skipped": cleaned["skipped"],
            "duplicates": cleaned["duplicates_in_file"],
            "errors": cleaned["errors"],
            "index_result": {"indexed": 0, "errors": []},
        }

    existing = db.query(Ticket.instruction).filter(Ticket.user_id == user_id).all()
    existing_questions = {normalize_question(row[0]) for row in existing}

    inserted_tickets: List[Ticket] = []
    duplicate_count = cleaned["duplicates_in_file"]

    for row in rows:
        question_key = normalize_question(row["instruction"])
        if question_key in existing_questions:
            duplicate_count += 1
            continue
        existing_questions.add(question_key)
        ticket = Ticket(user_id=user_id, **row)
        db.add(ticket)
        inserted_tickets.append(ticket)

    try:
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    index_result = bulk_index_tickets(user_id, inserted_tickets)
    return {
        "status": "success",
        "message": f"成功导入 {len(inserted_tickets)} 条工单",
        "inserted": len(inserted_tickets),
        "skipped": cleaned["skipped"],
        "duplicates": duplicate_count,
        "errors": cleaned["errors"],
        "index_result": index_result,
    }


def upload_support_docs(
    user_id: str,
    files: List[Any],
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    index_name = docs_index_name(user_id)
    ensure_supportops_index(index_name)

    session_key = session_id or str(uuid.uuid4()).replace("-", "")[:16]
    storage_dir = os.path.join(get_project_base_directory(), "storage/file/supportops_docs", user_id, session_key)
    os.makedirs(storage_dir, exist_ok=True)

    successful_files = []
    failed_files = []
    file_results = []
    indexed_chunks = 0
    before_count = _count_index_documents(index_name)

    for file in files:
        file_name = file.filename or "uploaded_doc"
        file_path = os.path.join(storage_dir, file_name)
        try:
            content = file.file.read()
            if not content:
                failed_files.append(f"{file_name}: 文件内容为空")
                file_results.append(
                    {
                        "file_name": file_name,
                        "status": "failed",
                        "parsed": 0,
                        "processed": 0,
                        "indexed": 0,
                        "errors": ["文件内容为空"],
                    }
                )
                continue
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            insert_result = execute_insert_process(file_path, file_name, index_name) or {}
            file_indexed = int(insert_result.get("indexed") or 0)
            indexed_chunks += file_indexed
            file_result = {
                "file_name": file_name,
                "status": insert_result.get("status", "failed"),
                "parsed": int(insert_result.get("parsed") or 0),
                "processed": int(insert_result.get("processed") or 0),
                "indexed": file_indexed,
                "errors": insert_result.get("errors") or [],
            }
            file_results.append(file_result)
            if file_indexed > 0 and file_result["status"] in {"success", "partial_success"}:
                successful_files.append(file_name)
            else:
                failed_files.append(f"{file_name}: 未写入可检索片段")
        except Exception as exc:
            failed_files.append(f"{file_name}: {str(exc)}")
            file_results.append(
                {
                    "file_name": file_name,
                    "status": "failed",
                    "parsed": 0,
                    "processed": 0,
                    "indexed": 0,
                    "errors": [str(exc)],
                }
            )

    after_count = _count_index_documents(index_name)
    status = "success" if successful_files and not failed_files else "partial_success" if successful_files else "failed"
    return {
        "status": status,
        "message": f"成功上传 {len(successful_files)} 个文档，写入 {indexed_chunks} 个检索片段，失败 {len(failed_files)} 个",
        "index_name": index_name,
        "successful_files": successful_files,
        "failed_files": failed_files,
        "file_results": file_results,
        "indexed_chunks": indexed_chunks,
        "total_chunks": after_count,
        "chunks_before": before_count,
    }
