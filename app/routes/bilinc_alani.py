from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.sanri_orchestrator import run_sanri

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])


class AskRequest(BaseModel):
    message: str
    session_id: str = "default"
    lang: str = "tr"


class AskResponse(BaseModel):
    answer: str
    response: str
    session_id: str
    prompt_version: str
    title: Optional[str] = None
    message: Optional[str] = None
    steps: Optional[List[str]] = None
    closing: Optional[str] = None


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    user_message = (req.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")

    return run_sanri(
        db=db,
        user_id=int(x_user_id),
        user_message=user_message,
        session_id=req.session_id,
        lang=req.lang,
    )


@router.get("/memory")
def get_memory(
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    try:
        rows = db.execute(
            text("""
                SELECT type, content, created_at
                FROM user_memory
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT 20
            """),
            {"uid": int(x_user_id)},
        ).mappings().all()

        return rows
    except Exception as e:
        print("GET MEMORY ERROR =", repr(e))
        return []


@router.get("/profile")
def get_profile(
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    try:
        row = db.execute(
            text("""
                SELECT user_id, data, updated_at
                FROM user_profiles
                WHERE user_id = :uid
                LIMIT 1
            """),
            {"uid": int(x_user_id)},
        ).mappings().first()

        if not row:
            return {
                "user_id": int(x_user_id),
                "data": {},
                "updated_at": None,
            }

        raw_data = row.get("data")
        if isinstance(raw_data, dict):
            parsed = raw_data
        else:
            import json
            try:
                parsed = json.loads(raw_data) if raw_data else {}
            except Exception:
                parsed = {}

        return {
            "user_id": row["user_id"],
            "data": parsed,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        }
    except Exception as e:
        print("GET PROFILE ERROR =", repr(e))
        return {
            "user_id": int(x_user_id),
            "data": {},
            "updated_at": None,
        }