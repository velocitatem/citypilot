"""Per-user chat persistence. Conversation ownership = user_id (tenant-scoped)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text

from db import get_engine


TITLE_MAX = 60


def _title_from_text(content: str) -> str:
    snippet = content.strip().splitlines()[0] if content.strip() else "New chat"
    return (snippet[:TITLE_MAX].rstrip() + "…") if len(snippet) > TITLE_MAX else (snippet or "New chat")


def create_conversation(user_id: str, title: Optional[str] = None) -> str:
    conversation_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO conversations (conversation_id, user_id, title)
                VALUES (:cid, :uid, :title)
                """
            ),
            {"cid": conversation_id, "uid": user_id, "title": title or "New chat"},
        )
    return conversation_id


def list_conversations(user_id: str) -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT conversation_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = :uid
                ORDER BY updated_at DESC
                """
            ),
            {"uid": user_id},
        ).all()
    return [
        {
            "conversation_id": str(r.conversation_id),
            "title": r.title,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


def get_conversation(conversation_id: str, user_id: str) -> dict:
    with get_engine().begin() as conn:
        head = conn.execute(
            text(
                """
                SELECT conversation_id, title, created_at, updated_at
                FROM conversations
                WHERE conversation_id = :cid AND user_id = :uid
                """
            ),
            {"cid": conversation_id, "uid": user_id},
        ).first()
        if head is None:
            raise HTTPException(status_code=404, detail="conversation not found")

        msgs = conn.execute(
            text(
                """
                SELECT message_id, role, content, agent_run_id, created_at
                FROM conversation_messages
                WHERE conversation_id = :cid
                ORDER BY created_at, message_id
                """
            ),
            {"cid": conversation_id},
        ).all()

    return {
        "conversation_id": str(head.conversation_id),
        "title": head.title,
        "created_at": head.created_at.isoformat(),
        "updated_at": head.updated_at.isoformat(),
        "messages": [
            {
                "message_id": str(m.message_id),
                "role": m.role,
                "content": m.content,
                "agent_run_id": str(m.agent_run_id) if m.agent_run_id else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


def assert_owner(conversation_id: str, user_id: str) -> None:
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM conversations WHERE conversation_id = :cid AND user_id = :uid"
            ),
            {"cid": conversation_id, "uid": user_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="conversation not found")


def append_message(
    conversation_id: str,
    role: str,
    content: str,
    agent_run_id: Optional[str] = None,
    set_title_if_empty: bool = False,
) -> str:
    message_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO conversation_messages
                    (message_id, conversation_id, role, content, agent_run_id)
                VALUES (:mid, :cid, :role, :content, :rid)
                """
            ),
            {
                "mid": message_id,
                "cid": conversation_id,
                "role": role,
                "content": content,
                "rid": agent_run_id,
            },
        )
        if set_title_if_empty:
            conn.execute(
                text(
                    """
                    UPDATE conversations
                    SET title = :title, updated_at = now()
                    WHERE conversation_id = :cid AND title = 'New chat'
                    """
                ),
                {"cid": conversation_id, "title": _title_from_text(content)},
            )
        conn.execute(
            text("UPDATE conversations SET updated_at = now() WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
    return message_id


def load_history(conversation_id: str) -> list[dict]:
    """Return (role, content) pairs in chronological order, mapped to OpenAI roles."""
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE conversation_id = :cid
                ORDER BY created_at, message_id
                """
            ),
            {"cid": conversation_id},
        ).all()
    return [
        {"role": "assistant" if r.role == "agent" else r.role, "content": r.content}
        for r in rows
        if r.content
    ]
