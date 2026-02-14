# app/routes/admin.py
import os
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text

from app.db import engine
from app.routes.auth import parse_token, COOKIE_NAME # auth.py içindeki token çözücü

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
ADMIN_KEY = (os.getenv("ADMIN_KEY") or "").strip()

def require_admin(request: Request):
    # 1) Gizli anahtar zorunlu
    key = request.query_params.get("key", "")
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2) Login cookie zorunlu
    token = request.cookies.get(COOKIE_NAME)
    user_id = parse_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 3) user email çek
    with engine.connect() as conn:
        row = conn.execute(text("SELECT email FROM users WHERE id = :id"), {"id": user_id}).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Unauthorized")

    email = (row[0] or "").strip().lower()

    if not ADMIN_EMAIL or email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"user_id": user_id, "email": email}

@router.get("/stats")
def stats(request: Request):
    require_admin(request)

    with engine.connect() as conn:
        total_users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        premium_users = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")).scalar() or 0
        today_users = conn.execute(text("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE")).scalar() or 0

    return {
        "total_users": int(total_users),
        "premium_users": int(premium_users),
        "today_users": int(today_users),
    }

@router.get("/users")
def users(request: Request, limit: int = 50):
    require_admin(request)

    limit = max(1, min(200, int(limit)))

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, email, is_premium, created_at
            FROM users
            ORDER BY created_at DESC NULLS LAST
            LIMIT :limit
        """), {"limit": limit}).fetchall()

    return {
        "users": [
            {
                "id": r[0],
                "email": r[1],
                "is_premium": bool(r[2]),
                "created_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]
    }