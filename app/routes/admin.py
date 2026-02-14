from fastapi import APIRouter, HTTPException
import os
import psycopg2

router = APIRouter(prefix="/api/admin", tags=["admin"])

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

def _conn():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL missing in service env")
    return psycopg2.connect(DATABASE_URL)

@router.get("/stats")
def admin_stats(key: str):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY missing in service env")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        conn = _conn()
        cur = conn.cursor()

        # Total
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]

        # Today (created_at yoksa fallback)
        try:
            cur.execute("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE")
            today = cur.fetchone()[0]
        except Exception:
            today = None

        # Premium (is_premium yoksa fallback)
        try:
            cur.execute("SELECT COUNT(*) FROM users WHERE is_premium = true")
            premium = cur.fetchone()[0]
        except Exception:
            premium = None

        cur.close()
        conn.close()

        return {
            "total_users": total,
            "today_users": today,
            "premium_users": premium,
            "note": "If today_users/premium_users is null => missing column or type mismatch."
        }

    except Exception as e:
        # Hata mesajını net döndürsün ki bir daha kör kalmayalım
        raise HTTPException(status_code=500, detail=f"admin_stats failed: {type(e).__name__}: {str(e)}")