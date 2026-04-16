# app/routes/events.py
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.event import Event
from app.services.auth import decode_token

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    session_id: str = "mobile-default"
    action: str
    domain: str = "app"
    meta: Dict[str, Any] = {}
    user_id: Optional[str] = None


def _extract_uid(authorization: Optional[str], payload_uid: Optional[str]) -> Optional[str]:
    if payload_uid and str(payload_uid).strip() and payload_uid != "anon":
        return str(payload_uid).strip()
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
        p = decode_token(token)
        if p and p.get("sub"):
            return str(p["sub"])
    return None


@router.post("/log")
def log_event(
    payload: EventIn,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    uid = _extract_uid(authorization, payload.user_id or x_user_id)
    e = Event(
        id=str(uuid.uuid4()),
        user_id=uid,
        action=payload.action,
        domain=payload.domain,
        meta={**payload.meta, "session_id": payload.session_id},
    )
    db.add(e)
    db.commit()
    return {"ok": True}