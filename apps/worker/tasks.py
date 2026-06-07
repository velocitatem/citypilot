import logging
import os
import time
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

log = logging.getLogger("worker.tasks")

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
    log.info("[refresh.news] starting")
    t0 = time.monotonic()
    count = refresh_news()
    log.info("[refresh.news] done upserted=%d elapsed=%.1fs", count, time.monotonic() - t0)
    return {"upserted": count}


@celery_app.task(name="refresh.datasets")
def refresh_datasets_task() -> dict:
    log.info("[refresh.datasets] starting")
    t0 = time.monotonic()
    count = refresh_datasets()
    log.info("[refresh.datasets] done upserted=%d elapsed=%.1fs", count, time.monotonic() - t0)
    return {"upserted": count}


@celery_app.task(name="agent.run", bind=True)
def agent_run_task(self, agent_run_id: str, prompt: str) -> dict:
    log.info("[agent.run] received agent_run_id=%s prompt_len=%d", agent_run_id, len(prompt))
    log.debug("[agent.run] prompt=%r", prompt[:500])

    t0 = time.monotonic()
    log.info("[agent.run] provisioning sandbox ...")
    try:
        sandbox = provision_sandbox(agent_run_id)
    except Exception as exc:
        log.exception("[agent.run] sandbox provisioning FAILED agent_run_id=%s", agent_run_id)
        mark_run_failed(agent_run_id, f"sandbox provisioning failed: {exc}")
        raise

    log.info("[agent.run] sandbox ready elapsed=%.1fs", time.monotonic() - t0)
    mark_run_running(agent_run_id)

    run_error: Exception | None = None
    result: dict = {"agent_run_id": agent_run_id, "status": "failed"}
    t1 = time.monotonic()
    try:
        log.info("[agent.run] starting agent agent_run_id=%s", agent_run_id)
        result = run_agent(agent_run_id, sandbox, prompt)
        log.info(
            "[agent.run] agent finished status=%s elapsed=%.1fs agent_run_id=%s",
            result.get("status"),
            time.monotonic() - t1,
            agent_run_id,
        )
    except Exception as exc:
        log.exception("[agent.run] agent raised agent_run_id=%s", agent_run_id)
        run_error = exc
    finally:
        log.info("[agent.run] destroying sandbox agent_run_id=%s", agent_run_id)
        destroy_sandbox(sandbox)

    if run_error is not None:
        mark_run_failed(agent_run_id, str(run_error))
        raise run_error

    log.info("[agent.run] syncing artifacts agent_run_id=%s workspace=%s", agent_run_id, sandbox.workspace)
    try:
        artifact_count = sync_run_artifacts(agent_run_id, sandbox.workspace)
        log.info("[agent.run] artifacts synced count=%d agent_run_id=%s", artifact_count, agent_run_id)
    except Exception:
        log.exception("[agent.run] artifact sync FAILED agent_run_id=%s", agent_run_id)
        raise

    mark_run_succeeded(agent_run_id)
    record_run_summary_message(agent_run_id, result.get("final_text", ""))
    log.info("[agent.run] complete total_elapsed=%.1fs agent_run_id=%s", time.monotonic() - t0, agent_run_id)
    return result
