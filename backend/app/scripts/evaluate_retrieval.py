#!/usr/bin/env python3
"""Retrieval evaluation: Recall@K / MRR on a question -> answer task.

Design (documented so the numbers are interpretable):

- Corpus: TweetSumm records (real customer-support dialogs, abstractive
  summaries). Each record contributes one document containing only the
  AGENT-side answer text.
- Queries: the CUSTOMER-side text of the same record. The only relevant
  document for a query is the answer from its own conversation
  (known-item retrieval). The task therefore measures question->answer
  matching, the same asymmetry the production similar-ticket search faces —
  never trivial string identity.
- Modes: keyword-only (BM25 over jieba tokens) vs hybrid (BM25 + dense kNN
  with DashScope embeddings, weighted fusion). Hybrid runs only with
  --with-embeddings and a valid API key.

A dedicated Elasticsearch index is created per run and deleted afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from service.retrieval.embedding import embedding_vector_field, generate_embedding
from service.retrieval.es_client import bulk_insert, ensure_index, get_es, refresh
from service.retrieval.search import hybrid_search
from service.retrieval.text_utils import fine_grained_tokenize, tokenize
from service.supportops.api_key_context import use_api_key_config
from service.supportops.dataset_adapters import TweetSummAdapter
from service.supportops.evaluation import retrieval_metrics
from service.supportops.tools import has_valid_dashscope_key

DEFAULT_DATASET_CANDIDATES = (
    APP_ROOT.parent.parent / "data" / "external" / "tweetsumm" / "final_test_tweetsum.jsonl",
    Path("/datasets/external/tweetsumm/final_test_tweetsum.jsonl"),
)


def resolve_dataset(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    for candidate in DEFAULT_DATASET_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit("未找到 TweetSumm 数据文件，请用 --dataset 指定路径")


def build_documents(records: List[Dict[str, Any]], index_name: str, with_embeddings: bool) -> List[Dict[str, Any]]:
    answers = [record["response"] for record in records]
    embeddings: List[Any] = [None] * len(answers)
    if with_embeddings:
        embeddings = generate_embedding(answers)
        if not isinstance(embeddings, list) or len(embeddings) != len(answers):
            embeddings = [None] * len(answers)
    documents = []
    for record, answer, embedding in zip(records, answers, embeddings):
        doc = {
            "id": record["external_id"],
            "content_ltks": tokenize(answer),
            "content_sm_ltks": fine_grained_tokenize(answer),
            "content_with_weight": answer,
            "title_tks": "",
            "doc_id": record["external_id"],
            "docnm": record["external_id"],
            "docnm_kwd": record["external_id"],
            "kb_id": index_name,
            "available_int": 1,
        }
        if embedding:
            doc[embedding_vector_field()] = embedding
        documents.append(doc)
    return documents


def run_queries(index_name: str, records: List[Dict[str, Any]], vector_weight: float, top_k: int) -> List[Dict[str, Any]]:
    cases = []
    for record in records:
        chunks = hybrid_search(index_name, record["instruction"], top_k=top_k, vector_weight=vector_weight)
        cases.append(
            {
                "relevant_ids": [record["external_id"]],
                "retrieved_ids": [chunk["doc_id"] for chunk in chunks],
            }
        )
    return cases


def evaluate(cases: List[Dict[str, Any]], top_k: int) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for k in (1, top_k):
        metrics.update(retrieval_metrics(cases, top_k=k))
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="SupportOps retrieval evaluation (Recall@K / MRR)")
    parser.add_argument("--dataset", type=Path, help="TweetSumm jsonl 文件路径")
    parser.add_argument("--limit", type=int, default=100, help="评测样本数上限")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--vector-weight", type=float, default=0.6)
    parser.add_argument("--with-embeddings", action="store_true", help="同时评测混合检索（消耗 Embedding API 调用）")
    parser.add_argument("--user-id", help="从数据库读取该用户的 active API Key（与生产一致的解析链路）")
    parser.add_argument("--keep-index", action="store_true", help="调试用：跑完不删评测索引")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    api_config = None
    if args.user_id:
        from service.supportops.api_key_service import get_active_api_key_config
        from utils.database import SessionLocal

        db = SessionLocal()
        try:
            api_config = get_active_api_key_config(db, str(args.user_id))
        finally:
            db.close()
        if not api_config:
            print(f"[warn] 用户 {args.user_id} 没有 active API Key")

    dataset = resolve_dataset(args.dataset)
    adapted = TweetSummAdapter().adapt(dataset.read_bytes(), dataset.name, limit=args.limit)
    records = [r for r in adapted.records if r.get("external_id")][: args.limit]
    if len(records) < 10:
        raise SystemExit(f"有效样本不足（{len(records)}），无法评测")

    with_embeddings = args.with_embeddings
    if with_embeddings:
        key_ok = has_valid_dashscope_key((api_config or {}).get("api_key")) if api_config else has_valid_dashscope_key()
        if key_ok:
            with use_api_key_config(api_config):
                key_ok = generate_embedding("probe") is not None  # real round-trip
        if not key_ok:
            print("[warn] Embedding 探活失败（API Key 缺失或无效），只评测关键词检索")
            with_embeddings = False

    index_name = f"supportops_eval_{uuid.uuid4().hex[:8]}"
    report: Dict[str, Any] = {
        "dataset": str(dataset),
        "corpus_size": len(records),
        "queries": len(records),
        "top_k": args.top_k,
        "task": "known-item question->answer retrieval (TweetSumm)",
        "modes": {},
    }
    try:
        with use_api_key_config(api_config):
            ensure_index(index_name)
            documents = build_documents(records, index_name, with_embeddings)
            errors = bulk_insert(index_name, documents)
            refresh(index_name)
            if errors:
                print(f"[warn] {len(errors)} 条文档索引失败")

            print(f"[keyword] querying {len(records)} cases ...")
            keyword_cases = run_queries(index_name, records, vector_weight=0.0, top_k=args.top_k)
            report["modes"]["keyword"] = evaluate(keyword_cases, args.top_k)

            if with_embeddings:
                print(f"[hybrid w={args.vector_weight}] querying {len(records)} cases ...")
                hybrid_cases = run_queries(index_name, records, vector_weight=args.vector_weight, top_k=args.top_k)
                report["modes"][f"hybrid_w{args.vector_weight}"] = evaluate(hybrid_cases, args.top_k)
    finally:
        if not args.keep_index:
            try:
                get_es().indices.delete(index=index_name)
            except Exception:
                pass

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
