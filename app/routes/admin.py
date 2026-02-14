from fastapi import APIRouter, HTTPException
import psycopg2
import os
from datetime import datetime, date

router = APIRouter(prefix="/api/admin", tags=["admin"])

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

def _conn():
    return psycopg2.connect(DATABASE_URL)

@router.get("/stats")
def admin_stats(key: str):
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = _conn()
    cur = conn.cursor()

    # toplam
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    # bugün
    cur.execute(
        "SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s",
        (date.today(),)
    )
    today = cur.fetchone()[0]

    # premium (varsa plan sütunu)
    cur.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium'")
    premium = cur.fetchone()[0]

    # son 10
    cur.execute(
        "SELECT email, created_at FROM users ORDER BY created_at DESC LIMIT 10"
    )
    latest = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "total": total,
        "today": today,
        "premium": premium,
        "latest": latest
    }