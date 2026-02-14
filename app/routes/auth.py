# app/routes/auth.py
from fastapi import APIRouter, Response, Request, HTTPException
from pydantic import BaseModel, EmailStr
import psycopg2
import os
import bcrypt
import hmac
import hashlib
import base64
import time

router = APIRouter(prefix="/api/auth", tags=["auth"])
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "change_me") # Railway env'e koy: güçlü bir secret

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
    sig = hmac.new(JWT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

def make_token(user_id: int) -> str:
    # basit imzalı token: uid.ts.sig
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
        # opsiyonel: süre kontrolü (30 gün)
        if int(time.time()) - int(ts) > COOKIE_MAX_AGE:
            return None
        return int(uid)
    except:
        return None

def set_auth_cookie(resp: Response, token: str):
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="none",
        domain=".asksanri.com",  
        path="/",
    )

def clear_auth_cookie(resp: Response):
    resp.delete_cookie(COOKIE_NAME, path="/", domain=".asksanri.com")

@router.post("/email/register")
def email_register(data: RegisterRequest, response: Response):
    email = data.email.lower().strip()
    password = data.password

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = _conn()
    try:
        cur = conn.cursor()

        # email var mı?
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered")

        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (email, hashed_pw),
        )
        user_id = cur.fetchone()[0]
        conn.commit()

        # kayıt olunca login say (cookie bas)
        token = make_token(user_id)
        set_auth_cookie(response, token)

        return {"success": True, "user_id": user_id}
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

@router.post("/email/login")
def email_login(data: LoginRequest, response: Response):
    email = data.email.lower().strip()
    password = data.password

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id, password_hash = row
        ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = make_token(user_id)
        set_auth_cookie(response, token)

        return {"success": True, "user_id": user_id}
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

@router.get("/me")
def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    user_id = parse_token(token) if token else None
    if not user_id:
        return {"authenticated": False}

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {"authenticated": False}
        email = row[0]
        return {"authenticated": True, "user_id": user_id, "email": email}
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"success": True}