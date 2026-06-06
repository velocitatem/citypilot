import os
import uuid

from fastapi import HTTPException, Request, Response
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
    user_id: str
    company_id: str
    role: str


def login_as_user(response: Response, user_id: str) -> SessionContext:
    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT user_id, company_id, role FROM users WHERE user_id = :uid"),
            {"uid": user_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="unknown user")

        session_id = str(uuid.uuid4())
        conn.execute(
            text("INSERT INTO sessions (session_id, user_id) VALUES (:sid, :uid)"),
            {"sid": session_id, "uid": row.user_id},
        )

    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return SessionContext(
        session_id=session_id,
        user_id=row.user_id,
        company_id=row.company_id,
        role=row.role,
    )


def require_session(request: Request) -> SessionContext:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="no session")

    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT s.session_id, u.user_id, u.company_id, u.role
                FROM sessions s
                JOIN users u ON u.user_id = s.user_id
                WHERE s.session_id = :sid
                """
            ),
            {"sid": session_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=401, detail="no session")
        conn.execute(
            text("UPDATE sessions SET last_seen = now() WHERE session_id = :sid"),
            {"sid": session_id},
        )

    return SessionContext(
        session_id=str(row.session_id),
        user_id=row.user_id,
        company_id=row.company_id,
        role=row.role,
    )


def list_users() -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT u.user_id, u.role, u.company_id, c.display_name AS company_name
                FROM users u
                JOIN companies c ON c.company_id = u.company_id
                ORDER BY u.company_id, u.role, u.user_id
                """
            )
        ).all()
    return [
        {
            "user_id": r.user_id,
            "role": r.role,
            "company_id": r.company_id,
            "company_name": r.company_name,
        }
        for r in rows
    ]
