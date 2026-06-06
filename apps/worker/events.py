import json
import logging
import os
import time
from typing import Any, Iterator

import redis


SYSTEM_PROMPT = """You analyze solar plant data for one user/company/role.

- The run-local database is **DuckDB**. Use DuckDB SQL dialect — Postgres-only
  functions like `to_char` are unavailable; use `strftime`, `date_trunc`,
  `make_date`, etc.
- Use list_tables / describe_table / query_db to explore the data.
- Data is already RBAC-filtered; do not add company_id predicates.
- For reports, produce real PDF/DOCX/XLSX via the document tools.
- Cite tables/columns used.
- When talking about an artifact in a summary do not mention the full unix path just the filename. For example, say "the report `report.docx`" not "the report `/tmp/abcd1234/report.docx`".
"""


log = logging.getLogger("agent.events")

STREAM_MAXLEN = 5000
STREAM_TTL_SECONDS = 24 * 3600
PREVIEW_LIMIT = 320


class EventBus:
    """Append typed RunEvents to the Redis stream `agent_run:{id}:events`."""

    def __init__(self, agent_run_id: str):
        self.stream_key = f"agent_run:{agent_run_id}:events"
        url = os.environ.get("CELERY_BROKER_URL")
        self.r = redis.Redis.from_url(url) if url else None
        self._ttl_set = False

    def emit(self, event: dict) -> None:
        event = {"ts": int(time.time() * 1000), **event}
        data = json.dumps(event, default=str)
        log.info("[%s] %s", self.stream_key, data[:400])
        if self.r is None:
            return
        try:
            self.r.xadd(self.stream_key, {"data": data}, maxlen=STREAM_MAXLEN, approximate=True)
            if not self._ttl_set:
                self.r.expire(self.stream_key, STREAM_TTL_SECONDS)
                self._ttl_set = True
        except Exception:
            log.exception("[%s] xadd failed", self.stream_key)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(content: Any) -> str:
    """Extract only true text segments; drop reasoning/function_call markers."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for p in content:
            if isinstance(p, dict) and (p.get("type") in (None, "text") and "text" in p):
                out.append(p["text"])
            elif isinstance(p, str):
                out.append(p)
        return "".join(out)
    return ""


def _preview(value: Any) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= PREVIEW_LIMIT else s[: PREVIEW_LIMIT] + "…"


def _tool_call(tc: Any) -> dict:
    return {"id": _attr(tc, "id"), "name": _attr(tc, "name"), "args": _attr(tc, "args")}


def chunk_to_events(chunk: Any) -> Iterator[dict]:
    """Map one LangGraph `.stream()` chunk to zero-or-more typed RunEvents.

    Middleware ticks (`TodoListMiddleware.after_model`, …) carry no user-visible
    info and are dropped at the source.
    """
    if not isinstance(chunk, dict):
        return
    for node, state in chunk.items():
        if "Middleware" in node or not isinstance(state, dict):
            continue
        for msg in state.get("messages") or []:
            role = _attr(msg, "type") or _attr(msg, "role")
            if role in ("ai", "assistant"):
                text = _text(_attr(msg, "content"))
                calls = [_tool_call(tc) for tc in (_attr(msg, "tool_calls") or []) if _attr(tc, "name")]
                if text or calls:
                    yield {"type": "model.message", "text": text, "tool_calls": calls}
            elif role == "tool":
                content = _text(_attr(msg, "content"))
                yield {
                    "type": "tool.result",
                    "call_id": _attr(msg, "tool_call_id") or "",
                    "name": _attr(msg, "name"),
                    "ok": not content.startswith("tool error:"),
                    "preview": _preview(content),
                }
