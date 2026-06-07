import json
import logging
import os
import threading
from typing import Iterator, Optional

from openai import OpenAI
from pydantic import BaseModel

from services.agent_runs import enqueue_agent_run
from services.conversations import (
    append_message,
    assert_owner,
    create_conversation,
    load_history,
)
from services.session import SessionContext


CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-5")
log = logging.getLogger("services.chat")

SYSTEM_PROMPT = """You are CityPilot, an orchestrator chat assistant for a smart-city data intelligence platform.

You help users — including planners, analysts, district officers, budget teams, and other city stakeholders — understand city data and make evidence-based decisions. For simple questions (clarifications, follow-ups, explanations), just respond conversationally.

IMPORTANT: You cannot generate files, run code, query databases, or produce charts/PDFs/Excel yourself. You are an orchestrator only. When the user asks for data analysis, reports, charts, maps, plots, or any file export, you MUST call `spawn_research_agent` immediately with a clear, self-contained task prompt. Do not describe what you will do — just call the tool. The research agent runs in a sandboxed environment with access to the user's role-filtered city data and will produce the actual files.

When talking about an artifact in a summary do not mention the full unix path just the filename. For example, say "the report `report.docx`" not "the report `/tmp/abcd1234/report.docx`". Do not mention the agent_run_id or any internal details.

The agent logs will be streamed in the UI. Once you call `spawn_research_agent`, briefly tell the user the task is underway."""


SPAWN_TOOL = {
    "type": "function",
    "function": {
        "name": "spawn_research_agent",
        "description": "Spawn the sandboxed research agent to run a data/reporting task against the user's data.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Self-contained task description for the research agent. Include any output format (pdf/docx/xlsx) the user asked for.",
                }
            },
            "required": ["prompt"],
        },
    },
}


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    content: str


_client_instance: Optional[OpenAI] = None
_client_lock = threading.Lock()


def _client() -> OpenAI:
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                api_key = os.environ["OPENAI_API_KEY"].strip()
                _client_instance = OpenAI(api_key=api_key)
    return _client_instance


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


def chat_stream(
    payload: ChatRequest,
    session: SessionContext,
) -> Iterator[bytes]:
    """Persist the user turn, stream the assistant reply, persist the assistant turn."""
    text_content = payload.content.strip()
    if not text_content:
        yield _sse({"type": "done"})
        return

    if payload.conversation_id:
        assert_owner(payload.conversation_id, session.session_id)
        conversation_id = payload.conversation_id
        created = False
    else:
        conversation_id = create_conversation(session.session_id)
        created = True

    history = load_history(conversation_id)

    user_write = threading.Thread(
        target=append_message,
        kwargs={
            "conversation_id": conversation_id,
            "role": "user",
            "content": text_content,
            "set_title_if_empty": True,
        },
        daemon=True,
    )
    user_write.start()

    yield _sse(
        {
            "type": "conversation",
            "conversation_id": conversation_id,
            "created": created,
        }
    )

    text_buffer: list[str] = []
    tool_calls: dict[int, dict] = {}
    spawned_run_id: Optional[str] = None

    try:
        client = _client()
        api_messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        api_messages.extend(history)
        api_messages.append({"role": "user", "content": text_content})

        stream = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=api_messages,
            tools=[SPAWN_TOOL],
            tool_choice="auto",
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                text_buffer.append(delta.content)
                yield _sse({"type": "text", "delta": delta.content})
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
    except Exception:
        log.exception("chat completion failed")
        msg = "Sorry, the chat model request failed. Check the backend logs and OPENAI_API_KEY configuration."
        user_write.join()
        append_message(conversation_id, role="agent", content=msg)
        yield _sse({"type": "text", "delta": msg})
        yield _sse({"type": "done"})
        return

    if tool_calls:
        assistant_msg: dict = {
            "role": "assistant",
            "content": "".join(text_buffer) or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args"] or "{}"},
                }
                for tc in tool_calls.values()
            ],
        }
        api_messages.append(assistant_msg)

        for tc in tool_calls.values():
            if tc["name"] != "spawn_research_agent":
                tool_result = {"error": f"unknown tool {tc['name']}"}
            else:
                try:
                    args = json.loads(tc["args"] or "{}")
                    agent_prompt = args.get("prompt", "").strip()
                    if not agent_prompt:
                        tool_result = {"error": "missing prompt"}
                    else:
                        agent_run_id = enqueue_agent_run(
                            session, agent_prompt, conversation_id=conversation_id
                        )
                        spawned_run_id = agent_run_id
                        tool_result = {"agent_run_id": agent_run_id, "status": "queued"}
                        yield _sse(
                            {
                                "type": "agent_spawned",
                                "agent_run_id": agent_run_id,
                                "prompt": agent_prompt,
                            }
                        )
                except Exception as exc:
                    tool_result = {"error": str(exc)}

            api_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_result),
                }
            )

        try:
            followup = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=api_messages,
                stream=True,
            )
            for chunk in followup:
                delta = chunk.choices[0].delta
                if delta.content:
                    text_buffer.append(delta.content)
                    yield _sse({"type": "text", "delta": delta.content})
        except Exception:
            log.exception("chat follow-up completion failed")
            msg = "\n\nThe research agent was queued, but the final chat response failed to stream."
            text_buffer.append(msg)
            yield _sse({"type": "text", "delta": msg})

    user_write.join()

    final_text = "".join(text_buffer)
    if final_text or spawned_run_id:
        append_message(
            conversation_id,
            role="agent",
            content=final_text,
            agent_run_id=spawned_run_id,
        )

    yield _sse({"type": "done"})
