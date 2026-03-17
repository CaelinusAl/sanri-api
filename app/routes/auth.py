# app/routes/auth.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------
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


# --------------------------------------------------
# CURRENT USER
# --------------------------------------------------
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

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# --------------------------------------------------
# REGISTER
# --------------------------------------------------
@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if not payload.email and not payload.phone:
        raise HTTPException(
            status_code=400,
            detail="Email or phone is required"
        )

    existing_user = None

    if payload.email:
        existing_user = db.query(User).filter(User.email == payload.email).first()

    if not existing_user and payload.phone:
        existing_user = db.query(User).filter(User.phone == payload.phone).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="User already registered")

    user = User(
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        name=payload.name,
        birth_date=payload.birth_date,
        role="free",
        plan="free",
        is_verified=False,
        is_premium=False,
        matrix_role_unlocked=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token({
        "user_id": user.id
    })

    return {
        "token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "name": user.name,
            "birth_date": user.birth_date,
            "is_verified": user.is_verified,
            "role": user.role,
            "plan": user.plan,
            "is_premium": user.is_premium,
            "matrix_role_unlocked": user.matrix_role_unlocked,
        },
    }


# --------------------------------------------------
# LOGIN
# --------------------------------------------------
@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    if not payload.email and not payload.phone:
        raise HTTPException(
            status_code=400,
            detail="Email or phone is required"
        )

    user = None

    if payload.email:
        user = db.query(User).filter(User.email == payload.email).first()

    if not user and payload.phone:
        user = db.query(User).filter(User.phone == payload.phone).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.password_hash:
        raise HTTPException(status_code=401, detail="Password login not available")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({
        "user_id": user.id
    })

    return {
        "token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "name": user.name,
            "birth_date": user.birth_date,
            "is_verified": user.is_verified,
            "role": user.role,
            "plan": user.plan,
            "is_premium": user.is_premium,
            "matrix_role_unlocked": user.matrix_role_unlocked,
        },
    }


# --------------------------------------------------
# ME
# --------------------------------------------------
@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "phone": current_user.phone,
        "name": current_user.name,
        "birth_date": current_user.birth_date,
        "is_verified": current_user.is_verified,
        "role": current_user.role,
        "plan": current_user.plan,
        "is_premium": current_user.is_premium,
        "premium_until": current_user.premium_until.isoformat() if current_user.premium_until else None,
        "premium_source": current_user.premium_source,
        "matrix_role_unlocked": current_user.matrix_role_unlocked,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
        "last_seen_at": current_user.last_seen_at.isoformat() if current_user.last_seen_at else None,
    }