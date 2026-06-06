import os
import uuid

from fastapi import Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from db import get_engine


SESSION_COOKIE = "session_id"


def _cookie_secure() -> bool:
    value = os.environ.get("SESSION_COOKIE_SECURE")
    if value is not None:
        return value.lower() in ("1", "true", "yes")
    return bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"))


def _cookie_samesite() -> str:
    return os.environ.get("SESSION_COOKIE_SAMESITE") or ("none" if _cookie_secure() else "lax")


class SessionContext(BaseModel):
    session_id: str


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=60 * 60 * 24 * 365,
        path="/",
    )


def get_or_create_session(request: Request, response: Response) -> SessionContext:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        with get_engine().begin() as conn:
            row = conn.execute(
                text("SELECT session_id FROM sessions WHERE session_id = :sid"),
                {"sid": session_id},
            ).first()
            if row:
                conn.execute(
                    text("UPDATE sessions SET last_seen = now() WHERE session_id = :sid"),
                    {"sid": session_id},
                )
                return SessionContext(session_id=session_id)

    session_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO sessions (session_id) VALUES (:sid)"),
            {"sid": session_id},
        )
    _set_session_cookie(response, session_id)
    return SessionContext(session_id=session_id)


def require_session(request: Request, response: Response) -> SessionContext:
    return get_or_create_session(request, response)
