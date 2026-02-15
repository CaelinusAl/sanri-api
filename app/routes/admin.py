# app/routes/admin.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
import os
import psycopg2

router = APIRouter(prefix="/api/admin", tags=["admin"])

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = (os.getenv("ADMIN_KEY") or "").strip()


def _conn():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL missing in service env")
    # connect_timeout ekleyelim (Railway bazen gecikir)
    return psycopg2.connect(DATABASE_URL, connect_timeout=8)


def _require_admin(key: str | None):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY missing in service env")
    if not key:
        raise HTTPException(status_code=401, detail="Missing key")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")


@router.get("/stats")
def admin_stats(key: str = Query(default=None, description="Admin key")):
    """
    Returns:
      total_users: int
      today_users: int
      premium_users: int
    """
    _require_admin(key)

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # Total users
                cur.execute("SELECT COUNT(*) FROM users;")
                total = int(cur.fetchone()[0] or 0)

                # Today users (created_at yoksa 0)
                today = 0
                try:
                    cur.execute("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE;")
                    today = int(cur.fetchone()[0] or 0)
                except Exception:
                    today = 0

                # Premium users (is_premium yoksa 0)
                premium = 0
                try:
                    cur.execute("SELECT COUNT(*) FROM users WHERE is_premium = true;")
                    premium = int(cur.fetchone()[0] or 0)
                except Exception:
                    premium = 0

        return {
            "total_users": total,
            "today_users": today,
            "premium_users": premium,
        }

    except psycopg2.Error as e:
        # DB hatalarını daha anlaşılır döndür
        raise HTTPException(
            status_code=500,
            detail=f"admin_stats db error: {getattr(e, 'pgcode', '')} {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"admin_stats failed: {type(e).__name__}: {str(e)}")


@router.get("/users")
def admin_users(
    key: str = Query(default=None, description="Admin key"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    Latest users list for panel.
    """
    _require_admin(key)

    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # created_at yoksa bile id üzerinden son kullanıcıları verir
                cur.execute(
                    """
                    SELECT id, email,
                           COALESCE(created_at, NOW()) as created_at,
                           COALESCE(is_premium, false) as is_premium,
                           COALESCE(plan, 'free') as plan
                    FROM users
                    ORDER BY id DESC
                    LIMIT %s OFFSET %s;
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()

        users = []
        for r in rows:
            users.append(
                {
                    "id": r[0],
                    "email": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "is_premium": bool(r[3]),
                    "plan": r[4],
                }
            )

        return {"users": users, "limit": limit, "offset": offset}

    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"admin_users db error: {getattr(e, 'pgcode', '')} {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"admin_users failed: {type(e).__name__}: {str(e)}")