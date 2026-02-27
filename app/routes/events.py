# app/routes/events.py
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.event import Event

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    session_id: str = "mobile-default"
    action: str                 # "screen_view" | "click" | "open" | ...
    domain: str = "app"         # "awakened_cities" | "matrix" | "ust_bilinc" | ...
    meta: Dict[str, Any] = {}   # { screen, code, intent, lang, ... }


@router.post("/log")
def log_event(payload: EventIn, db: Session = Depends(get_db), x_sanri_token: Optional[str] = Header(default=None)):
    # Şimdilik user_id yok -> None. Sonra auth bağlarız.
    e = Event(
        id=str(uuid.uuid4()),
        user_id=None,
        action=payload.action,
        domain=payload.domain,
        meta={**payload.meta, "session_id": payload.session_id, "token_present": bool(x_sanri_token)},
    )
    db.add(e)
    db.commit()
    return {"ok": True}