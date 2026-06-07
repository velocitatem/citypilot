import os
from dataclasses import dataclass

from sqlalchemy import text

from db import get_engine


@dataclass
class ArtifactRef:
    artifact_id: str
    run_id: str
    filename: str
    content_type: str
    size: int


def list_for_run(run_id: str, session_id: str) -> list[ArtifactRef]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT a.artifact_id, a.agent_run_id, a.filename, a.content_type, a.size_bytes
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
        )
        for r in rows
    ]


def get_artifact(run_id: str, artifact_id: str, session_id: str) -> tuple[ArtifactRef, bytes] | None:
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT a.artifact_id, a.agent_run_id, a.filename, a.content_type, a.size_bytes, a.data
                FROM artifacts a
                JOIN agent_runs r ON r.agent_run_id = a.agent_run_id
                WHERE a.agent_run_id = :rid AND a.artifact_id = :aid AND r.session_id = :sid
                """
            ),
            {"rid": run_id, "aid": artifact_id, "sid": session_id},
        ).first()
    if row is None:
        return None
    ref = ArtifactRef(
        artifact_id=str(row.artifact_id),
        run_id=str(row.agent_run_id),
        filename=row.filename,
        content_type=row.content_type,
        size=int(row.size_bytes),
    )
    return ref, bytes(row.data)
