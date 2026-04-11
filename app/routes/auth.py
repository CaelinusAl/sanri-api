from typing import Optional
from datetime import datetime
import base64
import io

import pyotp
import qrcode

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import (
    verify_password,
    hash_password,
    create_access_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# =========================================================
# SCHEMAS
# =========================================================

class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class Enable2FAIn(BaseModel):
    email: EmailStr


class Verify2FASetupIn(BaseModel):
    email: EmailStr
    code: str


class Verify2FALoginIn(BaseModel):
    email: EmailStr
    code: str


# =========================================================
# CURRENT USER
# =========================================================

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.execute(
        text("""
            SELECT
                id,
                email,
                role,
                two_fa_enabled,
                created_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": int(user_id)},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(user)


# =========================================================
# REGISTER
# =========================================================

@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    existing = db.execute(
        text("""
            SELECT id
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = hash_password(payload.password)

    user = db.execute(
        text("""
            INSERT INTO users (
                email,
                password_hash,
                two_fa_enabled
            )
            VALUES (
                :email,
                :password_hash,
                FALSE
            )
            RETURNING id, email, two_fa_enabled, created_at
        """),
        {
            "email": email,
            "password_hash": password_hash,
        },
    ).mappings().first()

    db.commit()

    try:
        from app.services.email_service import send_welcome_email
        send_welcome_email(email, step=0)
    except Exception:
        pass

    token = create_access_token({"sub": str(user["id"])})

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "two_fa_enabled": user["two_fa_enabled"],
            "created_at": str(user["created_at"]) if user.get("created_at") else None,
        },
    }


# =========================================================
# LOGIN
# =========================================================

@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    user = db.execute(
        text("""
            SELECT
                id,
                email,
                password_hash,
                two_fa_enabled
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong password")

    if user["two_fa_enabled"]:
        return {
            "requires_2fa": True,
            "email": user["email"],
            "user_id": user["id"],
        }

    token = create_access_token({"sub": str(user["id"])})

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "two_fa_enabled": user["two_fa_enabled"],
        },
    }


# =========================================================
# ME
# =========================================================

@router.get("/me")
def me(user=Depends(get_current_user)):
    return user


# =========================================================
# 2FA SETUP
# =========================================================

@router.post("/2fa/setup")
def setup_2fa(payload: Enable2FAIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    user = db.execute(
        text("""
            SELECT id, email
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        secret = pyotp.random_base32()

        db.execute(
            text("""
                UPDATE users
                SET two_fa_secret = :secret,
                    two_fa_enabled = FALSE
                WHERE id = :uid
            """),
            {
                "secret": secret,
                "uid": user["id"],
            },
        )
        db.commit()

        otp_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user["email"],
            issuer_name="Sanri",
        )

        qr = qrcode.make(otp_uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return {
            "secret": secret,
            "otp_uri": otp_uri,
            "qr_base64": qr_base64,
        }

    except Exception as e:
        print("2FA SETUP ERROR =", str(e))
        raise HTTPException(status_code=500, detail=f"2FA setup failed: {str(e)}")


# =========================================================
# 2FA VERIFY SETUP
# =========================================================

@router.post("/2fa/verify-setup")
def verify_2fa_setup(payload: Verify2FASetupIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    user = db.execute(
        text("""
            SELECT id, email, two_fa_secret
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user["two_fa_secret"]:
        raise HTTPException(status_code=400, detail="2FA secret missing")

    totp = pyotp.TOTP(user["two_fa_secret"])

    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    db.execute(
        text("""
            UPDATE users
            SET
                two_fa_enabled = TRUE,
                two_fa_confirmed_at = :confirmed_at
            WHERE id = :uid
        """),
        {
            "confirmed_at": datetime.utcnow(),
            "uid": user["id"],
        },
    )
    db.commit()

    return {
        "success": True,
        "message": "2FA enabled",
    }


# =========================================================
# 2FA VERIFY LOGIN
# =========================================================

@router.post("/2fa/verify-login")
def verify_2fa_login(payload: Verify2FALoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    user = db.execute(
        text("""
            SELECT
                id,
                email,
                two_fa_secret,
                two_fa_enabled
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user["two_fa_enabled"]:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not user["two_fa_secret"]:
        raise HTTPException(status_code=400, detail="2FA secret missing")

    totp = pyotp.TOTP(user["two_fa_secret"])

    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    token = create_access_token({"sub": str(user["id"])})

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "two_fa_enabled": user["two_fa_enabled"],
        },
    }