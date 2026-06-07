import logging
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import NotRequired, TypedDict

# basicConfig is a no-op if uvicorn already owns the root logger, so
# we set our app loggers' level directly so they propagate to uvicorn's handler.
for _name in ("services.chat", "services.agent_runs", "worker.tasks", "worker.sandbox", "worker.agent_runner"):
    logging.getLogger(_name).setLevel(logging.DEBUG)

from celery import Celery
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from db import get_engine
from routes import router


_INIT_SQL = Path(os.environ.get("INIT_SQL_PATH", str(Path(__file__).parent.parent / "scripts" / "init.sql")))


def _apply_schema() -> None:
    sql = _INIT_SQL.read_text()
    with get_engine().begin() as conn:
        conn.execute(text(sql))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_schema()
    yield


app = FastAPI(title="Invertix Agent Backend", lifespan=lifespan)
HEALTH_SOCKET_TIMEOUT_SECONDS = 1
HEALTH_INSPECT_TIMEOUT_SECONDS = 1
DEFAULT_CORS_ALLOW_ORIGIN_REGEX = (
    r"https://.*\.up\.railway\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+"
)
CORS_ALLOW_ORIGIN_REGEX = (
    os.environ.get("CORS_ALLOW_ORIGIN_REGEX")
    or DEFAULT_CORS_ALLOW_ORIGIN_REGEX
)


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


CORS_ALLOW_ORIGINS = _split_env_list(
    os.environ.get("CORS_ALLOW_ORIGINS") or os.environ.get("FRONTEND_ORIGIN")
)


class HealthCheckResult(TypedDict):
    status: str
    detail: NotRequired[str]


@lru_cache(maxsize=4)
def get_celery_client(broker_url: str, backend_url: str) -> Celery:
    return Celery("invertix-backend-health", broker=broker_url, backend=backend_url)


@lru_cache(maxsize=8)
def get_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(
        redis_url,
        socket_connect_timeout=HEALTH_SOCKET_TIMEOUT_SECONDS,
        socket_timeout=HEALTH_SOCKET_TIMEOUT_SECONDS,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> JSONResponse:
    checks: dict[str, HealthCheckResult] = {}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as exc:
        checks["postgres"] = {"status": "error", "detail": str(exc)}

    broker_url = os.environ.get("CELERY_BROKER_URL")
    backend_url = os.environ.get("CELERY_RESULT_BACKEND")
    redis_urls = {
        "redis": os.environ.get("REDIS_URL"),
        "celery_broker": broker_url,
        "celery_result_backend": backend_url,
    }
    for name, redis_url in redis_urls.items():
        if not redis_url:
            checks[name] = {"status": "error", "detail": "not configured"}
            continue
        try:
            get_redis_client(redis_url).ping()
            checks[name] = {"status": "ok"}
        except Exception as exc:
            checks[name] = {"status": "error", "detail": str(exc)}

    if not broker_url or not backend_url:
        checks["worker"] = {"status": "error", "detail": "celery is not fully configured"}
    else:
        try:
            celery_client = get_celery_client(broker_url, backend_url)
            workers = celery_client.control.inspect(timeout=HEALTH_INSPECT_TIMEOUT_SECONDS).ping()
            if workers:
                checks["worker"] = {"status": "ok"}
            else:
                checks["worker"] = {"status": "error", "detail": "no workers responding"}
        except Exception as exc:
            checks["worker"] = {"status": "error", "detail": str(exc)}

    overall_status = "ok" if all(check["status"] == "ok" for check in checks.values()) else "error"
    status_code = status.HTTP_200_OK if overall_status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content={"status": overall_status, "checks": checks})
