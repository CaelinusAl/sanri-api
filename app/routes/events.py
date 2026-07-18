# app/routes/events.py
import uuid
from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db import get_db
from app.models.event import Event

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    action: str = Field(min_length=1, max_length=100)
    domain: str = Field(default="app", max_length=100)
    meta: Dict[str, Any] = {}


@router.post("/log")
def log_event(
    payload: EventIn,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    e = Event(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=payload.action,
        domain=payload.domain,
        meta={**payload.meta, "session_id": str(payload.session_id)},
    )
    db.add(e)
    db.commit()
    return {"ok": True}