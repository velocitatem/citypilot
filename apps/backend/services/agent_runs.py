import os
import uuid
from functools import lru_cache

from celery import Celery
from sqlalchemy import text

from db import get_engine
from services.session import SessionContext


@lru_cache(maxsize=1)
def get_celery() -> Celery:
    return Celery(
        "invertix-backend",
        broker=os.environ["CELERY_BROKER_URL"],
        backend=os.environ["CELERY_RESULT_BACKEND"],
    )


def enqueue_agent_run(
    session: SessionContext,
    prompt: str,
    conversation_id: str | None = None,
) -> str:
    agent_run_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO agent_runs
                    (agent_run_id, session_id, user_id, company_id, role, conversation_id, prompt, status)
                VALUES (:rid, :sid, :uid, :cid, :role, :convid, :prompt, 'queued')
                """
            ),
            {
                "rid": agent_run_id,
                "sid": session.session_id,
                "uid": session.user_id,
                "cid": session.company_id,
                "role": session.role,
                "convid": conversation_id,
                "prompt": prompt,
            },
        )

    get_celery().send_task(
        "agent.run",
        kwargs={
            "agent_run_id": agent_run_id,
            "user_id": session.user_id,
            "company_id": session.company_id,
            "role": session.role,
            "prompt": prompt,
        },
    )
    return agent_run_id
