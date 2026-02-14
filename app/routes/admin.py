from fastapi import APIRouter, HTTPException
import os
import psycopg2

router = APIRouter(prefix="/api/admin", tags=["admin"])

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

def _conn():
    return psycopg2.connect(DATABASE_URL)

@router.get("/stats")
def admin_stats(key: str):
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE")
    today = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE is_premium = true")
    premium = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "total_users": total,
        "today_users": today,
        "premium_users": premium
    }