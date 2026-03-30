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
from app.services.email_service import (
    create_verification_code,
    verify_code,
    send_verification_email,
    send_password_reset_email,
)


def ensure_auth_tables(db_engine):
    """Auto-create verification_codes table and email_verified column if missing."""
    from sqlalchemy import text as _text, inspect
    with db_engine.connect() as conn:
        conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                email VARCHAR(255) NOT NULL,
                code VARCHAR(6) NOT NULL,
                type VARCHAR(20) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(_text("""
            DO $$ BEGIN
                ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
        """))
        conn.commit()


router = APIRouter(prefix="/auth", tags=["auth"])

from app.db import engine
try:
    ensure_auth_tables(engine)
except Exception as e:
    print(f"[AUTH] Table migration warning: {e}")


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


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    email: EmailStr
    code: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ResendVerificationIn(BaseModel):
    email: EmailStr


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
                is_premium,
                two_fa_enabled,
                created_at,
                email_verified
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
            RETURNING id, email, two_fa_enabled, role, is_premium, created_at
        """),
        {
            "email": email,
            "password_hash": password_hash,
        },
    ).mappings().first()

    db.commit()

    try:
        code = create_verification_code(db, user["id"], email, "email_verify")
        send_verification_email(email, code)
    except Exception as e:
        print(f"[AUTH] Verification email failed: {e}")

    token = create_access_token({"sub": str(user["id"])})

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role", "free"),
            "is_premium": bool(user.get("is_premium", False)),
            "two_fa_enabled": user["two_fa_enabled"],
            "email_verified": False,
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
                two_fa_enabled,
                role,
                is_premium,
                name,
                phone,
                email_verified
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
            "name": user.get("name"),
            "phone": user.get("phone"),
            "role": user.get("role", "free"),
            "is_premium": bool(user.get("is_premium", False)),
            "two_fa_enabled": user["two_fa_enabled"],
            "email_verified": bool(user.get("email_verified", False)),
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
            "role": user.get("role", "free"),
            "is_premium": bool(user.get("is_premium", False)),
            "two_fa_enabled": user["two_fa_enabled"],
        },
    }


# =========================================================
# EMAIL VERIFICATION
# =========================================================

@router.post("/email/verify")
def verify_email_code(payload: VerifyEmailIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    
    result = verify_code(db, email, payload.code.strip(), "email_verify")
    if not result:
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş kod.")
    
    db.execute(
        text("UPDATE users SET email_verified = TRUE WHERE id = :uid"),
        {"uid": result["user_id"]},
    )
    db.commit()
    
    token = create_access_token({"sub": str(result["user_id"])})
    
    user = db.execute(
        text("SELECT id, email, role, is_premium, two_fa_enabled FROM users WHERE id = :uid LIMIT 1"),
        {"uid": result["user_id"]},
    ).mappings().first()
    
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role", "free"),
            "is_premium": bool(user.get("is_premium", False)),
            "two_fa_enabled": user["two_fa_enabled"],
            "email_verified": True,
        },
    }


@router.post("/email/resend-verification")
def resend_verification(payload: ResendVerificationIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    
    user = db.execute(
        text("SELECT id, email_verified FROM users WHERE email = :email LIMIT 1"),
        {"email": email},
    ).mappings().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    
    if user.get("email_verified"):
        return {"ok": True, "message": "E-posta zaten doğrulanmış."}
    
    code = create_verification_code(db, user["id"], email, "email_verify")
    sent = send_verification_email(email, code)
    
    if not sent:
        print(f"[AUTH] Resend verification: code={code} for {email}")
    
    return {"ok": True, "message": "Doğrulama kodu gönderildi."}


# =========================================================
# FORGOT PASSWORD
# =========================================================

@router.post("/email/forgot-password")
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    
    user = db.execute(
        text("SELECT id FROM users WHERE email = :email LIMIT 1"),
        {"email": email},
    ).mappings().first()
    
    if not user:
        return {"ok": True, "message": "Eğer bu e-posta kayıtlıysa, sıfırlama kodu gönderildi."}
    
    code = create_verification_code(db, user["id"], email, "password_reset")
    sent = send_password_reset_email(email, code)
    
    if not sent:
        print(f"[AUTH] Password reset: code={code} for {email}")
    
    return {"ok": True, "message": "Eğer bu e-posta kayıtlıysa, sıfırlama kodu gönderildi."}


@router.post("/email/reset-password")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    
    if len(payload.password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı.")
    
    result = verify_code(db, email, payload.code.strip(), "password_reset")
    if not result:
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş kod.")
    
    password_hash = hash_password(payload.password.strip())
    
    db.execute(
        text("UPDATE users SET password_hash = :ph WHERE id = :uid"),
        {"ph": password_hash, "uid": result["user_id"]},
    )
    db.commit()
    
    return {"ok": True, "message": "Şifre başarıyla güncellendi."}


# =========================================================
# CHANGE PASSWORD (authenticated)
# =========================================================

@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı.")
    
    user = db.execute(
        text("SELECT password_hash FROM users WHERE id = :uid LIMIT 1"),
        {"uid": current_user["id"]},
    ).mappings().first()
    
    if not user or not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Mevcut şifre hatalı.")
    
    new_hash = hash_password(payload.new_password.strip())
    db.execute(
        text("UPDATE users SET password_hash = :ph WHERE id = :uid"),
        {"ph": new_hash, "uid": current_user["id"]},
    )
    db.commit()
    
    return {"ok": True, "message": "Şifre başarıyla değiştirildi."}


# =========================================================
# ADMIN: SET ROLE
# =========================================================

class SetRoleIn(BaseModel):
    target_user_id: int
    role: str

@router.post("/admin/set-role")
def admin_set_role(
    payload: SetRoleIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    caller_role = db.execute(
        text("SELECT role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": current_user["id"]},
    ).scalar()

    if caller_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    db.execute(
        text("UPDATE users SET role = :role WHERE id = :uid"),
        {"role": payload.role, "uid": payload.target_user_id},
    )
    db.commit()

    return {"ok": True, "user_id": payload.target_user_id, "role": payload.role}


# =========================================================
# BOOTSTRAP: first admin (one-time, hardcoded to user 29)
# =========================================================

@router.post("/bootstrap-admin")
def bootstrap_admin(db: Session = Depends(get_db)):
    BOOTSTRAP_UID = 29

    current = db.execute(
        text("SELECT role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": BOOTSTRAP_UID},
    ).scalar()

    if current == "admin":
        return {"ok": True, "message": "Already admin"}

    db.execute(
        text("UPDATE users SET role = 'admin', is_premium = TRUE WHERE id = :uid"),
        {"uid": BOOTSTRAP_UID},
    )
    db.commit()

    return {"ok": True, "user_id": BOOTSTRAP_UID, "role": "admin"}