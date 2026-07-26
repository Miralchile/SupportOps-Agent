import datetime
import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.ticket import Ticket
from models.dataset_import_job import DatasetImportJob
from service.retrieval.doc_parser import is_supported_file
from service.retrieval.es_client import count_documents
from service.retrieval.indexer import index_file
from service.supportops.similar_ticket_search import (
    bulk_index_tickets,
    docs_index_name,
    ensure_supportops_index,
)
from service.supportops.dataset_adapters import get_dataset_adapter
from service.supportops.tools import normalize_question

APP_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = os.getenv("SUPPORTOPS_STORAGE_DIR") or str(APP_ROOT / "storage" / "supportops_docs")


def _job_result(job: DatasetImportJob, message: str) -> Dict[str, Any]:
    return {
        "status": job.status,
        "message": message,
        "job_id": job.id,
        "dataset_name": job.dataset_name,
        "dataset_version": job.dataset_version,
        "source_type": job.source_type,
        "checksum": job.checksum,
        "total_rows": job.total_rows,
        "inserted": job.accepted_rows,
        "skipped": job.rejected_rows,
        "duplicates": job.duplicate_rows,
        "pii_redacted": job.pii_redacted_rows,
        "split_counts": job.split_counts or {},
        "errors": job.errors or [],
        "index_result": {"indexed": job.indexed_rows, "errors": []},
    }


def ingest_dataset_content(
    db: Session,
    user_id: str,
    dataset_name: str,
    filename: str,
    content: bytes,
    limit: int | None = None,
    with_embeddings: bool = False,
) -> Dict[str, Any]:
    checksum = hashlib.sha256(content).hexdigest()
    adapter = get_dataset_adapter(dataset_name)
    existing_job = (
        db.query(DatasetImportJob)
        .filter(
            DatasetImportJob.user_id == user_id,
            DatasetImportJob.dataset_name == adapter.dataset_name,
            DatasetImportJob.checksum == checksum,
        )
        .first()
    )
    if existing_job:
        # 复用历史批次信息，但"本次新增/去重"按本请求的实际情况报告
        result = _job_result(existing_job, "相同数据文件已经导入，本次未重复写入")
        result["duplicates"] = int(result.get("inserted") or 0)
        result["inserted"] = 0
        return result

    adapted = adapter.adapt(content, filename, limit=limit)
    rows = adapted.records
    job = DatasetImportJob(
        user_id=user_id,
        dataset_name=adapted.dataset_name,
        dataset_version=adapted.dataset_version,
        source_filename=filename,
        source_type=adapted.source_type,
        status="processing",
        checksum=checksum,
        import_options={"with_embeddings": with_embeddings},
        total_rows=len(rows) + adapted.rejected,
        rejected_rows=adapted.rejected,
        errors=adapted.errors,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if not rows:
        job.status = "failed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        return {
            "status": "failed",
            "message": "没有可导入的工单数据",
            "job_id": job.id,
            "inserted": 0,
            "skipped": adapted.rejected,
            "duplicates": 0,
            "errors": adapted.errors,
            "index_result": {"indexed": 0, "errors": []},
        }

    existing = db.query(Ticket.instruction, Ticket.content_hash).filter(Ticket.user_id == user_id).all()
    existing_questions = {normalize_question(row[0]) for row in existing}
    existing_hashes = {row[1] for row in existing if row[1]}

    inserted_tickets: List[Ticket] = []
    duplicate_count = 0
    split_counts: Dict[str, int] = {}
    pii_redacted_rows = 0

    for row in rows:
        question_key = normalize_question(row["instruction"])
        if question_key in existing_questions or row["content_hash"] in existing_hashes:
            duplicate_count += 1
            continue
        existing_questions.add(question_key)
        existing_hashes.add(row["content_hash"])
        split = row["dataset_split"]
        split_counts[split] = split_counts.get(split, 0) + 1
        pii_redacted_rows += int(row["pii_redacted"])
        ticket = Ticket(user_id=user_id, import_job_id=job.id, **row)
        db.add(ticket)
        inserted_tickets.append(ticket)

    try:
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        job = db.query(DatasetImportJob).filter(DatasetImportJob.id == job.id).first()
        if job:
            job.status = "failed"
            job.errors = list(job.errors or []) + ["数据库写入失败"]
            job.completed_at = datetime.datetime.utcnow()
            db.commit()
        raise

    index_result = bulk_index_tickets(user_id, inserted_tickets, include_embeddings=with_embeddings)
    job.accepted_rows = len(inserted_tickets)
    job.duplicate_rows = duplicate_count
    job.pii_redacted_rows = pii_redacted_rows
    job.indexed_rows = int(index_result.get("indexed") or 0)
    job.split_counts = split_counts
    job.errors = list(job.errors or []) + list(index_result.get("errors") or [])[:100]
    job.status = "success" if not index_result.get("errors") else "partial_success"
    job.completed_at = datetime.datetime.utcnow()
    db.commit()
    return _job_result(job, f"成功导入 {len(inserted_tickets)} 条工单，过滤 {duplicate_count} 条重复数据")


def ingest_ticket_csv(db: Session, user_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    return ingest_dataset_content(db, user_id, "supportops_csv", filename, content, with_embeddings=True)


def upload_support_docs(
    user_id: str,
    files: List[Any],
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    index_name = docs_index_name(user_id)
    ensure_supportops_index(index_name)

    session_key = session_id or str(uuid.uuid4()).replace("-", "")[:16]
    storage_dir = os.path.join(STORAGE_ROOT, str(user_id), session_key)
    os.makedirs(storage_dir, exist_ok=True)

    successful_files = []
    failed_files = []
    file_results = []
    indexed_chunks = 0
    before_count = count_documents(index_name)

    for file in files:
        # basename() guards against path traversal via crafted filenames.
        file_name = os.path.basename(file.filename or "").strip() or "uploaded_doc"
        file_path = os.path.join(storage_dir, file_name)
        try:
            if not is_supported_file(file_name):
                raise ValueError("不支持的文档类型（支持 PDF/DOCX/TXT/MD）")
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
            insert_result = index_file(file_path, file_name, index_name) or {}
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

    after_count = count_documents(index_name)
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
