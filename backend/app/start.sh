#!/bin/bash
# Container entrypoint: wait for PostgreSQL, then run the given command.
# Table creation itself happens inside the app on startup (utils.database.init_db).
set -e

echo "[start] waiting for PostgreSQL..."
python - <<'PY'
import os
import sys
import time

import psycopg

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("[start] DATABASE_URL is not set")
    sys.exit(1)

for attempt in range(1, 31):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print("[start] database is ready")
        sys.exit(0)
    except Exception as exc:
        print(f"[start] waiting for database ({attempt}/30): {exc}")
        time.sleep(2)
sys.exit(1)
PY

exec "$@"
