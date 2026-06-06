import asyncio
import json
import os
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from db import get_engine
from services.session import SESSION_COOKIE


XREAD_BLOCK_MS = 15_000


def _stream_key(run_id: str) -> str:
    return f"agent_run:{run_id}:events"


def _session_owns_run(run_id: str, session_id: str) -> bool:
    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT 1 FROM agent_runs WHERE agent_run_id = :rid AND session_id = :sid"),
            {"rid": run_id, "sid": session_id},
        ).first()
    return row is not None


def _decode(entry_id: bytes, fields: dict) -> tuple[str, dict]:
    raw = fields.get(b"data") or fields.get("data") or "{}"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        event = {"type": "raw", "raw": raw}
    eid = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
    return eid, event


def _sse_frame(eid: Optional[str], event_type: str, data: str) -> bytes:
    parts: list[str] = []
    if eid:
        parts.append(f"id: {eid}")
    parts.append(f"event: {event_type}")
    parts.append(f"data: {data}")
    return ("\n".join(parts) + "\n\n").encode("utf-8")


def _is_terminal(event: dict) -> bool:
    return event.get("type") == "run.finished"


async def stream_run_events(request: Request, run_id: str) -> StreamingResponse:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or not _session_owns_run(run_id, session_id):
        raise HTTPException(404, "run not found")

    cursor = request.headers.get("Last-Event-ID") or "0"

    async def gen() -> AsyncIterator[bytes]:
        client = aioredis.from_url(os.environ["CELERY_BROKER_URL"])
        stream = _stream_key(run_id)
        try:
            replay_min = "-" if cursor == "0" else f"({cursor}"
            history = await client.xrange(stream, min=replay_min, max="+")
            last = cursor
            for eid, fields in history:
                sid, event = _decode(eid, fields)
                yield _sse_frame(sid, event.get("type", "message"), json.dumps(event))
                last = sid
                if _is_terminal(event):
                    return

            while not await request.is_disconnected():
                resp = await client.xread({stream: last}, count=64, block=XREAD_BLOCK_MS)
                if not resp:
                    yield b": ping\n\n"
                    continue
                for _name, entries in resp:
                    for eid, fields in entries:
                        sid, event = _decode(eid, fields)
                        yield _sse_frame(sid, event.get("type", "message"), json.dumps(event))
                        last = sid
                        if _is_terminal(event):
                            return
        except asyncio.CancelledError:
            raise
        finally:
            await client.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
