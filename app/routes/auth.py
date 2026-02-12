from fastapi import APIRouter
from pydantic import BaseModel
import psycopg2
import os
import bcrypt

router = APIRouter(prefix="/api/auth", tags=["auth"])

DATABASE_URL = os.getenv("DATABASE_URL")

class RegisterRequest(BaseModel):
    email: str
    password: str

@router.post("/email/register")
def email_register(data: RegisterRequest):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    hashed_pw = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
        (data.email, hashed_pw),
    )

    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return {"success": True, "user_id": user_id}