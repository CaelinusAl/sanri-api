

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import verify_password, hash_password, create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    print("AUTH HEADER =", authorization)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)

    print("PAYLOAD =", payload)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    print("USER ID =", user_id)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT id FROM users WHERE email = :email LIMIT 1"),
        {"email": payload.email},
    ).mappings().first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    password_hash = hash_password(payload.password)

    user = db.execute(
        text("""
            INSERT INTO users (email, password_hash)
            VALUES (:email, :password_hash)
            RETURNING id, email
        """),
        {"email": payload.email, "password_hash": password_hash},
    ).mappings().first()

    db.commit()

    token = create_access_token({"sub": str(user["id"])})

    return {"token": token, "user": user}


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(
        text("""
            SELECT id, email, password_hash
            FROM users
            WHERE email = :email
            LIMIT 1
        """),
        {"email": payload.email},
    ).mappings().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong password")

    token = create_access_token({"sub": str(user["id"])})

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
        },
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user