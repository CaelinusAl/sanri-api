# app/routes/admin.py
import os
from fastapi import APIRouter, HTTPException
import psycopg2

router = APIRouter(prefix="/api/admin", tags=["admin"])

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

def _conn():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL missing")
    return psycopg2.connect(DATABASE_URL)

def _require_key(key: str):
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/stats")
def stats(key: str):
    _require_key(key)
    conn = _conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0] or 0

        # son 24 saat kayıt (created_at varsa)
        last_24h = None
        try:
            cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '24 hours'")
            last_24h = cur.fetchone()[0] or 0
        except:
            last_24h = None

        # premium kolonun varsa
        premium = None
        try:
            cur.execute("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
            premium = cur.fetchone()[0] or 0
        except:
            premium = None

        return {
            "total_users": total_users,
            "last_24h": last_24h,
            "premium_users": premium,
        }
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

@router.get("/users")
def users(key: str, limit: int = 50, offset: int = 0):
    _require_key(key)
    conn = _conn()
    try:
        cur = conn.cursor()
        # created_at yoksa ORDER BY id ile de iş görür
        try:
            cur.execute(
                "SELECT id, email, created_at FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
            return [{"id": r[0], "email": r[1], "created_at": (r[2].isoformat() if r[2] else None)} for r in rows]
        except:
            cur.execute(
                "SELECT id, email FROM users ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
            return [{"id": r[0], "email": r[1]} for r in rows]
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()