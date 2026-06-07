import logging
import os
import time

from deepagents import create_deep_agent

from context import RunContext
from events import EventBus, SYSTEM_PROMPT, chunk_to_events
from sandbox_provider import SANDBOX_SKILLS_DIR, SandboxHandle
from tools import build_tools

log = logging.getLogger("worker.agent_runner")


def _build_agent(ctx: RunContext):
    model = os.environ.get("AGENT_MODEL", "openai:gpt-5")
    tools = build_tools(ctx)
    log.info("[agent] building agent model=%s tools=%s", model, [getattr(t, "name", str(t)) for t in tools])
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        backend=ctx.backend,
        skills=[f"{SANDBOX_SKILLS_DIR}/"],
    )
    log.info("[agent] agent built agent=%r", type(agent).__name__)
    return agent


def run_agent(
    agent_run_id: str,
    sandbox: SandboxHandle,
    prompt: str,
) -> dict:
    ctx = RunContext(
        agent_run_id=agent_run_id,
        backend=sandbox.backend,
    )

    bus = EventBus(agent_run_id)
    bus.emit({"type": "run.started", "prompt": prompt})
    log.info("[agent] building agent for run agent_run_id=%s", agent_run_id)
    agent = _build_agent(ctx)

    final_text = ""
    chunk_count = 0
    event_count = 0
    tool_call_count = 0
    t0 = time.monotonic()

    try:
        log.info("[agent] starting stream agent_run_id=%s", agent_run_id)
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"configurable": {"thread_id": agent_run_id}},
        ):
            chunk_count += 1
            if chunk_count == 1:
                log.info("[agent] first chunk received elapsed=%.1fs agent_run_id=%s", time.monotonic() - t0, agent_run_id)
            log.debug("[agent] chunk #%d keys=%s", chunk_count, list(chunk.keys()) if isinstance(chunk, dict) else type(chunk).__name__)

            for event in chunk_to_events(chunk):
                event_count += 1
                etype = event.get("type")
                if etype == "model.message":
                    calls = event.get("tool_calls") or []
                    if calls:
                        tool_call_count += len(calls)
                        log.info("[agent] tool_calls=%s agent_run_id=%s", [c.get("name") for c in calls], agent_run_id)
                    if event.get("text"):
                        log.debug("[agent] model text (first 200): %r", event["text"][:200])
                        final_text = event["text"]
                elif etype == "tool.result":
                    log.info("[agent] tool_result name=%s ok=%s preview=%r", event.get("name"), event.get("ok"), (event.get("preview") or "")[:120])
                bus.emit(event)

    except Exception as e:
        log.exception("[agent] stream raised after %d chunks agent_run_id=%s", chunk_count, agent_run_id)
        bus.emit({"type": "run.finished", "status": "failed", "error": str(e)})
        raise

    elapsed = time.monotonic() - t0
    log.info(
        "[agent] stream complete chunks=%d events=%d tool_calls=%d elapsed=%.1fs agent_run_id=%s",
        chunk_count, event_count, tool_call_count, elapsed, agent_run_id,
    )
    bus.emit({"type": "run.finished", "status": "succeeded"})
    return {"agent_run_id": agent_run_id, "status": "succeeded", "final_text": final_text}


if __name__ == "__main__":
    import uuid

    from etl import build_role_filtered_package
    from sandbox_provider import provision_sandbox, destroy_sandbox

    agent_run_id = str(uuid.uuid4())
    prompt = os.environ.get(
        "AGENT_PROMPT",
        "List the available datasets, summarize what city data is present, and produce a brief PDF overview report. Put all outputs into the artifacts/ directory.",
    )

    sandbox = provision_sandbox(agent_run_id)
    try:
        result = run_agent(agent_run_id, sandbox, prompt)
        print("result:", result)
        print("workspace:", sandbox.workspace)
    finally:
        destroy_sandbox(sandbox)
