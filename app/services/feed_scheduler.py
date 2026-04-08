import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.system_feed import generate_and_store_feed
from app.db import SessionLocal

log = logging.getLogger("sanri.scheduler")
scheduler = BackgroundScheduler()

_job_status = {}


def _safe_run(label, fn):
    """Run a scheduled function, catch all exceptions so the scheduler survives."""
    db = SessionLocal()
    try:
        fn(db)
        _job_status[label] = {"ok": True, "last_run": __import__("datetime").datetime.utcnow().isoformat()}
        log.info("Scheduler job '%s' completed", label)
    except Exception as exc:
        _job_status[label] = {"ok": False, "error": str(exc)[:200], "last_run": __import__("datetime").datetime.utcnow().isoformat()}
        log.exception("Scheduler job '%s' failed: %s", label, exc)
    finally:
        db.close()


def morning_feed():
    _safe_run("morning_feed", lambda db: generate_and_store_feed(db, "tr"))


def midday_feed():
    _safe_run("midday_feed", lambda db: generate_and_store_feed(db, "tr"))


def night_feed():
    _safe_run("night_feed", lambda db: generate_and_store_feed(db, "tr"))


def daily_feeling_job():
    from app.services.daily_feeling_service import generate_daily_feeling
    _safe_run("daily_feeling", lambda db: generate_daily_feeling(db))


def start_scheduler():
    if scheduler.running:
        log.info("Scheduler already running, skipping")
        return

    scheduler.add_job(morning_feed, "cron", hour=6, minute=0, id="morning_feed", replace_existing=True)
    scheduler.add_job(midday_feed, "cron", hour=12, minute=0, id="midday_feed", replace_existing=True)
    scheduler.add_job(night_feed, "cron", hour=21, minute=0, id="night_feed", replace_existing=True)
    scheduler.add_job(daily_feeling_job, "cron", hour=8, minute=0, id="daily_feeling_morning", replace_existing=True)
    scheduler.add_job(daily_feeling_job, "cron", hour=20, minute=0, id="daily_feeling_evening", replace_existing=True)

    scheduler.start()
    log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


def get_scheduler_health():
    """Returns scheduler status for the /health/scheduler endpoint."""
    return {
        "running": scheduler.running,
        "jobs": [
            {"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()
        ],
        "last_results": _job_status,
    }
