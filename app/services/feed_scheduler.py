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


def welcome_email_job():
    _safe_run("welcome_emails", _process_welcome_emails)


def _process_welcome_emails(db):
    from sqlalchemy import text
    from app.services.email_service import send_welcome_email, WELCOME_EMAILS

    for step_idx in range(1, len(WELCOME_EMAILS)):
        delay_hours = WELCOME_EMAILS[step_idx]["delay_hours"]
        rows = db.execute(text("""
            SELECT u.id, u.email
            FROM users u
            WHERE u.created_at <= NOW() - INTERVAL ':hours hours'
              AND u.created_at > NOW() - INTERVAL ':hours_max hours'
              AND NOT EXISTS (
                  SELECT 1 FROM welcome_email_log w
                  WHERE w.user_id = u.id AND w.step = :step
              )
            LIMIT 50
        """.replace(":hours hours", f"{delay_hours} hours")
           .replace(":hours_max hours", f"{delay_hours + 12} hours")),
            {"step": step_idx},
        ).mappings().all()

        for row in rows:
            try:
                send_welcome_email(row["email"], step=step_idx)
                db.execute(text(
                    "INSERT INTO welcome_email_log (user_id, step, email) VALUES (:uid, :step, :email)"
                ), {"uid": row["id"], "step": step_idx, "email": row["email"]})
                db.commit()
            except Exception as exc:
                db.rollback()
                log.warning("Welcome email step=%d user=%s failed: %s", step_idx, row["email"], exc)


def start_scheduler():
    if scheduler.running:
        log.info("Scheduler already running, skipping")
        return

    scheduler.add_job(morning_feed, "cron", hour=6, minute=0, id="morning_feed", replace_existing=True)
    scheduler.add_job(midday_feed, "cron", hour=12, minute=0, id="midday_feed", replace_existing=True)
    scheduler.add_job(night_feed, "cron", hour=21, minute=0, id="night_feed", replace_existing=True)
    scheduler.add_job(daily_feeling_job, "cron", hour=8, minute=0, id="daily_feeling_morning", replace_existing=True)
    scheduler.add_job(daily_feeling_job, "cron", hour=20, minute=0, id="daily_feeling_evening", replace_existing=True)
    scheduler.add_job(welcome_email_job, "interval", hours=2, id="welcome_emails", replace_existing=True)

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
