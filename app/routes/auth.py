from typing import Optional

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


# -----------------------------
# SCHEMAS
# -----------------------------
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


# -----------------------------
# CURRENT USER
# -----------------------------
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
                created_at
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": int(user_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(row)


# -----------------------------
# REGISTER
# -----------------------------
@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if not payload.email and not payload.phone:
        raise HTTPException(status_code=400, detail="Email or phone required")

    if payload.email:
        existing_email = db.execute(
            text("SELECT id FROM users WHERE email = :email LIMIT 1"),
            {"email": payload.email},
        ).mappings().first()

        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")

    if payload.phone:
        existing_phone = db.execute(
            text("SELECT id FROM users WHERE phone = :phone LIMIT 1"),
            {"phone": payload.phone},
        ).mappings().first()

        if existing_phone:
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
                matrix_role_unlocked
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
                FALSE
            )
            RETURNING id, email, phone, name
        """),
        {
            "email": payload.email,
            "phone": payload.phone,
            "password_hash": password_hash,
            "name": payload.name,
            "birth_date": payload.birth_date,
        },
    ).mappings().first()

    db.commit()

    token = create_access_token({"user_id": str(created["id"])})

    return {
        "token": token,
        "user": {
            "id": created["id"],
            "email": created["email"],
            "phone": created["phone"],
            "name": created["name"],
        },
    }


# -----------------------------
# LOGIN
# -----------------------------
@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    if not payload.email and not payload.phone:
        raise HTTPException(status_code=400, detail="Email or phone required")

    row = None

    if payload.email:
        row = db.execute(
            text("""
                SELECT id, email, phone, name, password_hash
                FROM users
                WHERE email = :email
                LIMIT 1
            """),
            {"email": payload.email},
        ).mappings().first()

    elif payload.phone:
        row = db.execute(
            text("""
                SELECT id, email, phone, name, password_hash
                FROM users
                WHERE phone = :phone
                LIMIT 1
            """),
            {"phone": payload.phone},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    if not row["password_hash"]:
        raise HTTPException(status_code=500, detail="Password hash missing")

    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong password")

    token = create_access_token({
    "sub": str(row["id"])
})

    return {
        "token": token,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "phone": row["phone"],
            "name": row["name"],
        },
    }


# -----------------------------
# ME
# -----------------------------
@router.get("/me")
def me(user=Depends(get_current_user)):
    return user