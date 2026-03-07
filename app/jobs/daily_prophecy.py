from sqlalchemy import text

from app.db import SessionLocal
from app.services.memory import get_user_memory
from app.services.insight_engine import build_user_insight
from app.services.daily_prophecy_engine import predict_daily_state, build_daily_prophecy
from app.services.push import send_push


def run_daily_prophecy():

    db = SessionLocal()

    try:

        rows = db.execute(text("""
            SELECT id, name, device_token, COALESCE(lang,'tr') as lang
            FROM users
            WHERE device_token IS NOT NULL
        """)).mappings().all()

        for row in rows:

            uid = int(row["id"])
            name = row.get("name")
            token = row.get("device_token")
            lang = row.get("lang")

            try:
                memory = get_user_memory(db, uid)
            except:
                memory = []

            try:
                insight = build_user_insight(db, uid)
            except:
                insight = {}

            state = predict_daily_state(memory, insight)

            prophecy = build_daily_prophecy(
                state,
                lang,
                name
            )

            send_push(
                token,
                "Sanrı",
                prophecy
            )

    finally:
        db.close()


if __name__ == "__main__":
    run_daily_prophecy()