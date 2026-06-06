import os
from dataclasses import dataclass
from urllib.parse import urlparse

from minio import Minio
from sqlalchemy import text

from db import get_engine


def _parse_minio_endpoint(raw: str) -> tuple[str, bool]:
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.netloc, parsed.scheme == "https"
    return raw.split("/", 1)[0], False


@dataclass
class ArtifactRef:
    artifact_id: str
    run_id: str
    filename: str
    content_type: str
    size: int
    object_key: str


class ArtifactStore:
    def __init__(self) -> None:
        self.bucket = os.environ.get("MINIO_BUCKET", "artifacts")
        endpoint, inferred_secure = _parse_minio_endpoint(os.environ["MINIO_ENDPOINT"])
        secure_env = os.environ.get("MINIO_SECURE")
        secure = secure_env.lower() == "true" if secure_env is not None else inferred_secure
        self.client = Minio(
            endpoint,
            access_key=os.environ["MINIO_ROOT_USER"],
            secret_key=os.environ["MINIO_ROOT_PASSWORD"],
            secure=secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def object_key(self, run_id: str, artifact_id: str, filename: str) -> str:
        return f"{run_id}/{artifact_id}/{filename}"

    def list_for_run(self, run_id: str, session_id: str) -> list[ArtifactRef]:
        with get_engine().begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT a.artifact_id, a.agent_run_id, a.filename, a.content_type, a.size_bytes, a.object_key
                    FROM artifacts a
                    JOIN agent_runs r ON r.agent_run_id = a.agent_run_id
                    WHERE a.agent_run_id = :rid AND r.session_id = :sid
                    ORDER BY a.created_at, a.artifact_id
                    """
                ),
                {"rid": run_id, "sid": session_id},
            ).all()
        return [
            ArtifactRef(
                artifact_id=str(r.artifact_id),
                run_id=str(r.agent_run_id),
                filename=r.filename,
                content_type=r.content_type,
                size=int(r.size_bytes),
                object_key=r.object_key,
            )
            for r in rows
        ]

    def get(self, run_id: str, artifact_id: str, session_id: str) -> ArtifactRef | None:
        with get_engine().begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT a.artifact_id, a.agent_run_id, a.filename, a.content_type, a.size_bytes, a.object_key
                    FROM artifacts a
                    JOIN agent_runs r ON r.agent_run_id = a.agent_run_id
                    WHERE a.agent_run_id = :rid AND a.artifact_id = :aid AND r.session_id = :sid
                    """
                ),
                {"rid": run_id, "aid": artifact_id, "sid": session_id},
            ).first()
        if row is None:
            return None
        return ArtifactRef(
            artifact_id=str(row.artifact_id),
            run_id=str(row.agent_run_id),
            filename=row.filename,
            content_type=row.content_type,
            size=int(row.size_bytes),
            object_key=row.object_key,
        )
