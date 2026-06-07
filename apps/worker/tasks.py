import os
from celery import Celery
from celery.schedules import crontab

from agent_runner import run_agent
from artifacts import (
    mark_run_failed,
    mark_run_running,
    mark_run_succeeded,
    record_run_summary_message,
    sync_run_artifacts,
)
from sandbox_provider import provision_sandbox, destroy_sandbox

celery_app = Celery(
    "invertix",
    broker=os.environ["CELERY_BROKER_URL"],
    backend=os.environ["CELERY_RESULT_BACKEND"],
)

# HKT is UTC+8; run refresh jobs in the early morning local time.
celery_app.conf.beat_schedule = {
    # Scrape recent HKFP headlines every day at 02:00 HKT (18:00 UTC prev day).
    "refresh-news-daily": {
        "task": "refresh.news",
        "schedule": crontab(hour=18, minute=0),
    },
    # Re-sync HK open-data catalog every Monday at 03:00 HKT (19:00 UTC prev day).
    "refresh-datasets-weekly": {
        "task": "refresh.datasets",
        "schedule": crontab(hour=19, minute=0, day_of_week=0),
    },
}
celery_app.conf.timezone = "UTC"


from refresh import refresh_news, refresh_datasets


@celery_app.task(name="refresh.news")
def refresh_news_task() -> dict:
    count = refresh_news()
    return {"upserted": count}


@celery_app.task(name="refresh.datasets")
def refresh_datasets_task() -> dict:
    count = refresh_datasets()
    return {"upserted": count}


@celery_app.task(name="agent.run", bind=True)
def agent_run_task(self, agent_run_id: str, prompt: str) -> dict:
    sandbox = provision_sandbox(agent_run_id)
    mark_run_running(agent_run_id)
    run_error: Exception | None = None
    result: dict = {"agent_run_id": agent_run_id, "status": "failed"}
    try:
        result = run_agent(agent_run_id, sandbox, prompt)
    except Exception as exc:
        run_error = exc
    finally:
        destroy_sandbox(sandbox)

    if run_error is not None:
        mark_run_failed(agent_run_id, str(run_error))
        raise run_error

    sync_run_artifacts(agent_run_id, sandbox.workspace)
    mark_run_succeeded(agent_run_id)
    record_run_summary_message(agent_run_id, result.get("final_text", ""))
    return result
