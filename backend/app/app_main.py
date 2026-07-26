import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from router import supportops_rt, user_rt
from utils.database import init_db

logger = logging.getLogger("supportops.app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create missing tables on boot; retry briefly in case the database
    # container is still starting.
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            init_db()
            last_error = None
            break
        except Exception as exc:  # pragma: no cover - startup resilience
            last_error = exc
            logger.warning("Database init attempt %d/5 failed: %s", attempt, exc)
            time.sleep(2)
    if last_error is not None:
        raise last_error
    yield


app = FastAPI(title="SupportOps Agent API", root_path=os.getenv("ROOT_PATH", ""), lifespan=lifespan)

# Comma-separated origin allowlist; "*" (default) is convenient for local use.
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],  # credentials + wildcard is invalid per CORS spec
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_rt.router)
app.include_router(supportops_rt.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
