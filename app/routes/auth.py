# app/routes/auth.py
import os
import time
import base64
import hmac
import hashlib
import bcrypt
import psycopg2

from fastapi import APIRouter, Response, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/auth", tags=["auth"])

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET") # Railway env'e mutlaka koy

COOKIE_NAME = "sanri_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30 # 30 gün


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _conn():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL missing")
    return psycopg2.connect(DATABASE_URL)


def _token_sign(payload: str) -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET missing")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")


def make_token(user_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}"
    sig = _token_sign(payload)
    return f"{payload}.{sig}"


def parse_token(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        uid, ts, sig = parts
        payload = f"{uid}.{ts}"

        if not hmac.compare_digest(_token_sign(payload), sig):
            return None

        # 30 gün TTL
        if int(time.time()) - int(ts) > COOKIE_MAX_AGE:
            return None

        return int(uid)
    except Exception:
        return None


def _get_token_from_header_or_cookie(request: Request, authorization: str | None) -> str | None:
    # 1) Authorization: Bearer <token>
    if authorization and authorization.lower().startswith("bearer "):
        val = authorization.split(" ", 1)[1].strip()
        return val or None
    # 2) Cookie
    return request.cookies.get(COOKIE_NAME)


def set_auth_cookie(resp: Response, token: str):
    # Cross-site (Vercel->Railway) cookie için:
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True, # HTTPS şart
        samesite="none", # cross-site cookie
        path="/",
    )


def clear_auth_cookie(resp: Response):
    resp.delete_cookie(COOKIE_NAME, path="/")


@router.post("/email/register")
def email_register(data: RegisterRequest):
    email = data.email.lower().strip()
    password = data.password

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = _conn()
    cur = conn.cursor()
    try:
        # email var mı?
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered")

        # create user
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (email, hashed_pw),
        )
        user_id = cur.fetchone()[0]

        # created_at db default; ama last_seen/login varsa set edelim
        try:
            cur.execute("UPDATE users SET last_login_at = NOW(), last_seen_at = NOW() WHERE id = %s", (user_id,))
        except Exception:
            pass

        conn.commit()

        token = make_token(user_id)
        resp = JSONResponse({"success": True, "user_id": user_id, "token": token})
        set_auth_cookie(resp, token)
        return resp

    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


@router.post("/email/login")
def email_login(data: LoginRequest):
    email = data.email.lower().strip()
    password = data.password

    conn = _conn()
    cur = conn.cursor()
    try:
        # user çek
        cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id, password_hash = row

        ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # ✅ login timestamp + seen
        try:
            cur.execute("UPDATE users SET last_login_at = NOW(), last_seen_at = NOW() WHERE id = %s", (user_id,))
        except Exception:
            pass

        conn.commit()

        token = make_token(user_id)
        resp = JSONResponse({"success": True, "user_id": user_id, "token": token})
        set_auth_cookie(resp, token)
        return resp

    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


@router.get("/me")
def me(request: Request, authorization: str | None = Header(default=None)):
    token = _get_token_from_header_or_cookie(request, authorization)
    user_id = parse_token(token) if token else None
    if not user_id:
        return {"authenticated": False}

    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {"authenticated": False}

        # ✅ seen timestamp
        try:
            cur.execute("UPDATE users SET last_seen_at = NOW() WHERE id = %s", (user_id,))
            conn.commit()
        except Exception:
            pass

        return {"authenticated": True, "user_id": user_id, "email": row[0]}

    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"success": True}


@router.get("/debug-auth")
def debug_auth(request: Request, authorization: str | None = Header(default=None)):
    token = _get_token_from_header_or_cookie(request, authorization)
    return {
        "has_cookie": COOKIE_NAME in request.cookies,
        "has_auth_header": bool(authorization),
        "token_prefix": (token[:18] if token else None),
    }