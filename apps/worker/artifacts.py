import mimetypes
import os
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

MAX_ERROR_LENGTH = 4000


@lru_cache(maxsize=1)
def _engine() -> Engine:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True, future=True)


def _parse_minio_endpoint(raw: str) -> tuple[str, bool]:
    # MinIO SDK requires bare host[:port]; strip scheme/path if present.
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.netloc, parsed.scheme == "https"
    return raw.split("/", 1)[0], False


@lru_cache(maxsize=1)
def _store() -> tuple[Minio, str]:
    bucket = os.environ.get("MINIO_BUCKET", "artifacts")
    endpoint, inferred_secure = _parse_minio_endpoint(os.environ["MINIO_ENDPOINT"])
    secure_env = os.environ.get("MINIO_SECURE")
    secure = secure_env.lower() == "true" if secure_env is not None else inferred_secure
    client = Minio(
        endpoint,
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=secure,
    )
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return client, bucket


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _object_key(run_id: str, artifact_id: str, filename: str) -> str:
    return f"{run_id}/{artifact_id}/{filename}"


def sync_run_artifacts(agent_run_id: str, package_dir: Path) -> int:
    root = package_dir / "artifacts"
    if not root.exists():
        return 0

    client, bucket = _store()
    inserted = 0
    with _engine().begin() as conn:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            artifact_id = str(uuid.uuid4())
            rel = path.relative_to(root).as_posix()
            object_key = _object_key(agent_run_id, artifact_id, rel)
            client.fput_object(
                bucket_name=bucket,
                object_name=object_key,
                file_path=str(path),
                content_type=_content_type(path),
            )
            conn.execute(
                text(
                    """
                    INSERT INTO artifacts
                        (artifact_id, agent_run_id, filename, content_type, size_bytes, object_key)
                    VALUES (:artifact_id, :run_id, :filename, :content_type, :size_bytes, :object_key)
                    """
                ),
                {
                    "artifact_id": artifact_id,
                    "run_id": agent_run_id,
                    "filename": rel,
                    "content_type": _content_type(path),
                    "size_bytes": path.stat().st_size,
                    "object_key": object_key,
                },
            )
            inserted += 1
    return inserted


def mark_run_running(agent_run_id: str) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE agent_runs
                SET status = 'running', started_at = COALESCE(started_at, now()), error = NULL
                WHERE agent_run_id = :rid
                """
            ),
            {"rid": agent_run_id},
        )


def mark_run_succeeded(agent_run_id: str) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE agent_runs
                SET status = 'succeeded', finished_at = now(), error = NULL
                WHERE agent_run_id = :rid
                """
            ),
            {"rid": agent_run_id},
        )


def record_run_summary_message(agent_run_id: str, final_text: str) -> None:
    """Append the agent's final output (plus artifact list) to the parent
    conversation so the meta-agent picks it up via load_history next turn."""
    with _engine().begin() as conn:
        run = conn.execute(
            text("SELECT conversation_id FROM agent_runs WHERE agent_run_id = :rid"),
            {"rid": agent_run_id},
        ).first()
        if not run or not run.conversation_id:
            return

        content = (final_text or "").strip()
        if not content:
            return

        conn.execute(
            text(
                """
                INSERT INTO conversation_messages
                    (message_id, conversation_id, role, content, agent_run_id)
                VALUES (:mid, :cid, 'agent', :content, :rid)
                """
            ),
            {
                "mid": str(uuid.uuid4()),
                "cid": run.conversation_id,
                "content": content,
                "rid": agent_run_id,
            },
        )
        conn.execute(
            text("UPDATE conversations SET updated_at = now() WHERE conversation_id = :cid"),
            {"cid": run.conversation_id},
        )


def mark_run_failed(agent_run_id: str, error: str) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE agent_runs
                SET status = 'failed', finished_at = now(), error = :error
                WHERE agent_run_id = :rid
                """
            ),
            {"rid": agent_run_id, "error": error[:MAX_ERROR_LENGTH]},
        )
