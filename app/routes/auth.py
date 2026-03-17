from typing import Optional
from random import randint
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# =========================================================
# SCHEMAS
# =========================================================
class RegisterIn(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str
    name: Optional[str] = None
    birth_date: Optional[str] = None


class LoginIn(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str


class RequestEmailCodeIn(BaseModel):
    email: EmailStr


class RequestPhoneCodeIn(BaseModel):
    phone: str


class VerifyPhoneCodeIn(BaseModel):
    phone: str
    code: str


class Enable2FAIn(BaseModel):
    user_id: int
    channel: str # "email" | "phone"


class Verify2FAIn(BaseModel):
    user_id: int
    channel: str # "email" | "phone"
    code: str


# =========================================================
# HELPERS
# =========================================================
def _utc_now():
    return datetime.now(timezone.utc)


def _generate_code(length: int = 6) -> str:
    start = 10 ** (length - 1)
    end = (10 ** length) - 1
    return str(randint(start, end))


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _get_user_by_email(db: Session, email: str):
    return db.execute(
        text("""
            SELECT
                id,
                email,
                phone,
                password_hash,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                premium_until,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel,
                created_at
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": email},
    ).mappings().first()


def _get_user_by_phone(db: Session, phone: str):
    return db.execute(
        text("""
            SELECT
                id,
                email,
                phone,
                password_hash,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                premium_until,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel,
                created_at
            FROM users
            WHERE phone = :phone
            LIMIT 1
        """),
        {"phone": phone},
    ).mappings().first()


def _get_user_by_id(db: Session, user_id: int):
    return db.execute(
        text("""
            SELECT
                id,
                email,
                phone,
                password_hash,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                premium_until,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel,
                created_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": user_id},
    ).mappings().first()


def _public_user(row):
    return {
        "id": row["id"],
        "email": row["email"],
        "phone": row["phone"],
        "name": row["name"],
        "birth_date": row["birth_date"],
        "role": row["role"],
        "plan": row["plan"],
        "is_premium": row["is_premium"],
        "premium_until": row["premium_until"],
        "matrix_role_unlocked": row["matrix_role_unlocked"],
        "is_email_verified": row.get("is_email_verified"),
        "is_phone_verified": row.get("is_phone_verified"),
        "is_2fa_enabled": row.get("is_2fa_enabled"),
        "two_fa_channel": row.get("two_fa_channel"),
        "created_at": row["created_at"],
    }


def _issue_token(user_id: int) -> str:
    return create_access_token({"user_id": str(user_id)})


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

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    row = _get_user_by_id(db, int(user_id))
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(row)


# =========================================================
# REGISTER
# =========================================================
@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip() if payload.email else None
    phone = _normalize_phone(payload.phone) if payload.phone else None

    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email or phone required")

    if email and _get_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="Email already registered")

    if phone and _get_user_by_phone(db, phone):
        raise HTTPException(status_code=400, detail="Phone already registered")

    password_hash = hash_password(payload.password)

    created = db.execute(
        text("""
            INSERT INTO users (
                email,
                phone,
                password_hash,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel
            )
            VALUES (
                :email,
                :phone,
                :password_hash,
                :name,
                :birth_date,
                'free',
                'free',
                FALSE,
                FALSE,
                FALSE,
                FALSE,
                FALSE,
                NULL
            )
            RETURNING
                id,
                email,
                phone,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                premium_until,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel,
                created_at
        """),
        {
            "email": email,
            "phone": phone,
            "password_hash": password_hash,
            "name": payload.name,
            "birth_date": payload.birth_date,
        },
    ).mappings().first()

    db.commit()

    token = _issue_token(created["id"])

    return {
        "token": token,
        "user": _public_user(created),
    }


# =========================================================
# LOGIN
# =========================================================
@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip() if payload.email else None
    phone = _normalize_phone(payload.phone) if payload.phone else None

    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email or phone required")

    row = None

    if email:
        row = _get_user_by_email(db, email)
    elif phone:
        row = _get_user_by_phone(db, phone)

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    if not row["password_hash"]:
        raise HTTPException(status_code=500, detail="Password hash missing")

    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong password")

    # 2FA açıksa burada hemen token vermiyoruz
    if row.get("is_2fa_enabled"):
        code = _generate_code(6)
        expires_at = _utc_now() + timedelta(minutes=10)

        db.execute(
            text("""
                UPDATE users
                SET two_fa_code = :code,
                    two_fa_expires_at = :expires_at
                WHERE id = :uid
            """),
            {
                "code": code,
                "expires_at": expires_at,
                "uid": row["id"],
            },
        )
        db.commit()

        # TODO: gerçek provider bağlanınca burada gönder
        # email => send email
        # phone => send sms

        return {
            "requires_2fa": True,
            "user_id": row["id"],
            "channel": row.get("two_fa_channel") or "email",
            "message": "2FA verification code created",
            "debug_code": code, # production'da kaldır
        }

    token = _issue_token(row["id"])

    return {
        "token": token,
        "user": _public_user(row),
    }


# =========================================================
# ME
# =========================================================
@router.get("/me")
def me(user=Depends(get_current_user)):
    return _public_user(user)


# =========================================================
# EMAIL VERIFY
# =========================================================
@router.post("/request-email-code")
def request_email_code(payload: RequestEmailCodeIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    row = _get_user_by_email(db, email)

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    code = _generate_code(6)
    expires_at = _utc_now() + timedelta(minutes=10)

    db.execute(
        text("""
            UPDATE users
            SET email_verify_code = :code,
                email_verify_expires_at = :expires_at
            WHERE id = :uid
        """),
        {
            "code": code,
            "expires_at": expires_at,
            "uid": row["id"],
        },
    )
    db.commit()

    # TODO: gerçek mail gönderimi buraya
    return {
        "success": True,
        "message": "Email verification code created",
        "debug_code": code, # production'da kaldır
    }


@router.post("/verify-email")
def verify_email(payload: VerifyEmailIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    row = _get_user_by_email(db, email)

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    verify_row = db.execute(
        text("""
            SELECT id, email_verify_code, email_verify_expires_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": row["id"]},
    ).mappings().first()

    if not verify_row or not verify_row["email_verify_code"]:
        raise HTTPException(status_code=400, detail="No verification code found")

    if verify_row["email_verify_code"] != payload.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    if verify_row["email_verify_expires_at"] and verify_row["email_verify_expires_at"] < _utc_now():
        raise HTTPException(status_code=400, detail="Verification code expired")

    db.execute(
        text("""
            UPDATE users
            SET is_email_verified = TRUE,
                email_verify_code = NULL,
                email_verify_expires_at = NULL
            WHERE id = :uid
        """),
        {"uid": row["id"]},
    )
    db.commit()

    return {"success": True, "message": "Email verified"}


# =========================================================
# PHONE VERIFY
# =========================================================
@router.post("/request-phone-code")
def request_phone_code(payload: RequestPhoneCodeIn, db: Session = Depends(get_db)):
    phone = _normalize_phone(payload.phone)
    row = _get_user_by_phone(db, phone)

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    code = _generate_code(6)
    expires_at = _utc_now() + timedelta(minutes=10)

    db.execute(
        text("""
            UPDATE users
            SET phone_verify_code = :code,
                phone_verify_expires_at = :expires_at
            WHERE id = :uid
        """),
        {
            "code": code,
            "expires_at": expires_at,
            "uid": row["id"],
        },
    )
    db.commit()

    # TODO: gerçek sms gönderimi buraya
    return {
        "success": True,
        "message": "Phone verification code created",
        "debug_code": code, # production'da kaldır
    }


@router.post("/verify-phone")
def verify_phone(payload: VerifyPhoneCodeIn, db: Session = Depends(get_db)):
    phone = _normalize_phone(payload.phone)
    row = _get_user_by_phone(db, phone)

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    verify_row = db.execute(
        text("""
            SELECT id, phone_verify_code, phone_verify_expires_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": row["id"]},
    ).mappings().first()

    if not verify_row or not verify_row["phone_verify_code"]:
        raise HTTPException(status_code=400, detail="No verification code found")

    if verify_row["phone_verify_code"] != payload.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    if verify_row["phone_verify_expires_at"] and verify_row["phone_verify_expires_at"] < _utc_now():
        raise HTTPException(status_code=400, detail="Verification code expired")

    db.execute(
        text("""
            UPDATE users
            SET is_phone_verified = TRUE,
                phone_verify_code = NULL,
                phone_verify_expires_at = NULL
            WHERE id = :uid
        """),
        {"uid": row["id"]},
    )
    db.commit()

    return {"success": True, "message": "Phone verified"}


# =========================================================
# 2FA ENABLE / VERIFY
# =========================================================
@router.post("/enable-2fa")
def enable_2fa(payload: Enable2FAIn, db: Session = Depends(get_db)):
    if payload.channel not in ("email", "phone"):
        raise HTTPException(status_code=400, detail="Channel must be email or phone")

    row = _get_user_by_id(db, payload.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.channel == "email" and not row["email"]:
        raise HTTPException(status_code=400, detail="User has no email")

    if payload.channel == "phone" and not row["phone"]:
        raise HTTPException(status_code=400, detail="User has no phone")

    db.execute(
        text("""
            UPDATE users
            SET is_2fa_enabled = TRUE,
                two_fa_channel = :channel
            WHERE id = :uid
        """),
        {
            "channel": payload.channel,
            "uid": payload.user_id,
        },
    )
    db.commit()

    return {"success": True, "message": "2FA enabled"}


@router.post("/verify-2fa")
def verify_2fa(payload: Verify2FAIn, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT
                id,
                email,
                phone,
                name,
                birth_date,
                role,
                plan,
                is_premium,
                premium_until,
                matrix_role_unlocked,
                is_email_verified,
                is_phone_verified,
                is_2fa_enabled,
                two_fa_channel,
                two_fa_code,
                two_fa_expires_at,
                created_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": payload.user_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    if not row["is_2fa_enabled"]:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if row["two_fa_channel"] != payload.channel:
        raise HTTPException(status_code=400, detail="Wrong 2FA channel")

    if not row["two_fa_code"]:
        raise HTTPException(status_code=400, detail="No 2FA code found")

    if row["two_fa_code"] != payload.code:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    if row["two_fa_expires_at"] and row["two_fa_expires_at"] < _utc_now():
        raise HTTPException(status_code=400, detail="2FA code expired")

    db.execute(
        text("""
            UPDATE users
            SET two_fa_code = NULL,
                two_fa_expires_at = NULL
            WHERE id = :uid
        """),
        {"uid": payload.user_id},
    )
    db.commit()

    token = _issue_token(row["id"])

    return {
        "token": token,
        "user": _public_user(row),
    }