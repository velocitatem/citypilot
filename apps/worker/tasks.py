import os
from celery import Celery

from agent_runner import run_agent
from artifacts import (
    mark_run_failed,
    mark_run_running,
    mark_run_succeeded,
    record_run_summary_message,
    sync_run_artifacts,
)
from sandbox_provider import provision_sandbox, destroy_sandbox
from etl import build_role_filtered_package

celery_app = Celery(
    "invertix",
    broker=os.environ["CELERY_BROKER_URL"],
    backend=os.environ["CELERY_RESULT_BACKEND"],
)


@celery_app.task(name="agent.run", bind=True)
def agent_run_task(self, agent_run_id: str, user_id: str, company_id: str, role: str, prompt: str) -> dict:
    package_dir = build_role_filtered_package(agent_run_id, user_id, company_id, role)
    sandbox = provision_sandbox(agent_run_id, package_dir)
    mark_run_running(agent_run_id)
    run_error: Exception | None = None
    result: dict = {"agent_run_id": agent_run_id, "status": "failed"}
    try:
        result = run_agent(agent_run_id, sandbox, prompt, user_id, company_id, role)
    except Exception as exc:
        run_error = exc
    finally:
        destroy_sandbox(sandbox)

    if run_error is not None:
        mark_run_failed(agent_run_id, str(run_error))
        raise run_error

    sync_run_artifacts(agent_run_id, package_dir)
    mark_run_succeeded(agent_run_id)
    record_run_summary_message(agent_run_id, result.get("final_text", ""))
    return result
