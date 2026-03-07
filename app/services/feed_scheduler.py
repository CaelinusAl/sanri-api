from apscheduler.schedulers.background import BackgroundScheduler
from app.services.system_feed import generate_and_store_feed
from app.db import SessionLocal

scheduler = BackgroundScheduler()


def morning_feed():
    db = SessionLocal()
    try:
        generate_and_store_feed(db, "tr")
    finally:
        db.close()


def midday_feed():
    db = SessionLocal()
    try:
        generate_and_store_feed(db, "tr")
    finally:
        db.close()


def night_feed():
    db = SessionLocal()
    try:
        generate_and_store_feed(db, "tr")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(morning_feed, "cron", hour=6, minute=0)
    scheduler.add_job(midday_feed, "cron", hour=12, minute=0)
    scheduler.add_job(night_feed, "cron", hour=21, minute=0)

    scheduler.start()