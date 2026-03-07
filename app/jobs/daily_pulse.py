# app/jobs/daily_pulse.py
from sqlalchemy import text

from app.db import SessionLocal
from app.services.memory import get_user_memory
from app.services.insight_engine import build_user_insight
from app.services.pulse_engine import predict_daily_state, build_daily_message
from app.services.push import send_push


def run_daily_pulse():
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id, device_token, COALESCE(lang, 'tr') AS lang
                FROM users
                WHERE device_token IS NOT NULL
            """)
        ).mappings().all()

        for row in rows:
            uid = int(row["id"])
            token = row["device_token"]
            lang = row["lang"] or "tr"

            try:
                memory = get_user_memory(db, uid)
            except Exception:
                memory = []

            try:
                insight = build_user_insight(db, uid)
            except Exception:
                insight = {}

            state = predict_daily_state(memory, insight)
            body = build_daily_message(state, lang)
            send_push(token, "Sanrı", body)

    finally:
        db.close()


if __name__ == "__main__":
    run_daily_pulse()