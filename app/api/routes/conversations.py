from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.core.config import Settings, get_settings
from app.core.logging import log_migration_metric
from app.db import get_db
from app.models.v1 import V1Conversation
from app.schemas.v1 import ConversationCreate, ConversationResponse, ConversationSummary, MessageResponse, SessionCloseRequest


router = APIRouter(prefix="/v1/conversations", tags=["v1-conversations"])


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(payload: ConversationCreate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    row = V1Conversation(user_id=UUID(user_id), **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: UUID, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    row = db.scalar(
        select(V1Conversation).where(V1Conversation.id == conversation_id, V1Conversation.user_id == UUID(user_id))
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found"})
    return row


@router.post("/{conversation_id}/close", response_model=ConversationSummary)
def close_conversation(
    conversation_id: UUID,
    payload: SessionCloseRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.v1_session_close_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "session_close_not_enabled", "message": "V1 session close is not enabled"},
        )
    row = db.scalar(
        select(V1Conversation).where(
            V1Conversation.id == conversation_id,
            V1Conversation.user_id == UUID(user_id),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found"})
    if row.closed_at is None:
        row.close_summary = payload.model_dump()
        row.closed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    log_migration_metric(
        "session_close",
        route="v1",
        status="success",
        session_close_success=True,
    )
    return row
