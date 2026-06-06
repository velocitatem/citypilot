import os

from deepagents import create_deep_agent

from context import RunContext
from events import EventBus, SYSTEM_PROMPT, chunk_to_events
from sandbox_provider import SANDBOX_SKILLS_DIR, SandboxHandle
from tools import build_tools


def _build_agent(ctx: RunContext):
    return create_deep_agent(
        model=os.environ.get("AGENT_MODEL", "openai:gpt-5"),
        tools=build_tools(ctx),
        system_prompt=SYSTEM_PROMPT,
        backend=ctx.backend,
        skills=[f"{SANDBOX_SKILLS_DIR}/"],
    )


def run_agent(
    agent_run_id: str,
    sandbox: SandboxHandle,
    prompt: str,
    user_id: str,
    company_id: str,
    role: str,
) -> dict:
    ctx = RunContext(
        agent_run_id=agent_run_id,
        user_id=user_id,
        company_id=company_id,
        role=role,
        backend=sandbox.backend,
    )

    bus = EventBus(agent_run_id)
    bus.emit({"type": "run.started", "prompt": prompt})
    agent = _build_agent(ctx)

    final_text = ""
    try:
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"configurable": {"thread_id": agent_run_id}},
        ):
            for event in chunk_to_events(chunk):
                bus.emit(event)
                if event.get("type") == "model.message" and event.get("text"):
                    final_text = event["text"]
    except Exception as e:
        bus.emit({"type": "run.finished", "status": "failed", "error": str(e)})
        raise

    bus.emit({"type": "run.finished", "status": "succeeded"})
    return {"agent_run_id": agent_run_id, "status": "succeeded", "final_text": final_text}


if __name__ == "__main__":
    import uuid

    from etl import build_role_filtered_package
    from sandbox_provider import provision_sandbox, destroy_sandbox

    agent_run_id = str(uuid.uuid4())
    user_id = os.environ.get("AGENT_USER_ID", "company_1_admin")
    company_id = os.environ.get("AGENT_COMPANY_ID", "company_1")
    role = os.environ.get("AGENT_ROLE", "company_admin")
    prompt = os.environ.get(
        "AGENT_PROMPT",
        "List the available datasets, summarize what city data is present, and produce a brief PDF overview report. Put all outputs into the artifacts/ directory.",
    )

    package_dir = build_role_filtered_package(agent_run_id, user_id, company_id, role)
    sandbox = provision_sandbox(agent_run_id, package_dir)
    try:
        result = run_agent(agent_run_id, sandbox, prompt, user_id, company_id, role)
        print("result:", result)
        print("workspace:", sandbox.workspace)
    finally:
        destroy_sandbox(sandbox)
