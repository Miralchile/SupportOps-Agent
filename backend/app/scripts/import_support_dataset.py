#!/usr/bin/env python3
"""Import an approved local dataset file through the production ingestion path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.supportops.api_key_context import use_api_key_config
from service.supportops.api_key_service import get_active_api_key_config
from service.supportops.data_ingestion import ingest_dataset_content
from utils.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SupportOps datasets with provenance and quality controls")
    parser.add_argument("--dataset", required=True, choices=("supportops_csv", "bitext", "msdialog", "tweetsumm"))
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--with-embeddings", action="store_true", help="Generate embeddings during import (may incur API cost)")
    args = parser.parse_args()

    if not args.file.is_file():
        parser.error(f"file does not exist: {args.file}")
    content = args.file.read_bytes()
    db = SessionLocal()
    try:
        with use_api_key_config(get_active_api_key_config(db, args.user_id)):
            result = ingest_dataset_content(
                db,
                str(args.user_id),
                args.dataset,
                args.file.name,
                content,
                with_embeddings=args.with_embeddings,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
