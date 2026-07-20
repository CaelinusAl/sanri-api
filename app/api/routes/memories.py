from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db import get_db
from app.models.v1 import V1Conversation, V1Memory, V1Project
from app.schemas.v1 import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_service import create_memory


router = APIRouter(prefix="/v1/memories", tags=["v1-memories"])


@router.post("", response_model=MemoryResponse, status_code=201)
def save_memory(payload: MemoryCreate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    if not payload.consent:
        raise HTTPException(status_code=400, detail={"code": "memory_consent_required", "message": "Memory consent is required"})
    owner_id = UUID(user_id)
    if payload.conversation_id and db.scalar(
        select(V1Conversation.id).where(
            V1Conversation.id == payload.conversation_id,
            V1Conversation.user_id == owner_id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found"})
    if payload.project_id and db.scalar(
        select(V1Project.id).where(
            V1Project.id == payload.project_id,
            V1Project.user_id == owner_id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": "Project not found"})
    return create_memory(
        db,
        user_id,
        payload.content,
        payload.memory_type,
        source=payload.source,
        category=payload.category,
        confidence=payload.confidence,
        conversation_id=str(payload.conversation_id) if payload.conversation_id else None,
        project_id=str(payload.project_id) if payload.project_id else None,
        approval_status="approved",
    )


@router.get("", response_model=list[MemoryResponse])
def list_memories(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    statement = (
        select(V1Memory)
        .where(
            V1Memory.user_id == UUID(user_id),
            V1Memory.deleted_at.is_(None),
        )
        .order_by(V1Memory.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(statement))


@router.get("/search", response_model=list[MemoryResponse])
def search_memories(
    q: str | None = Query(default=None, max_length=200),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    statement = (
        select(V1Memory)
        .where(
            V1Memory.user_id == UUID(user_id),
            V1Memory.deleted_at.is_(None),
        )
        .order_by(V1Memory.created_at.desc())
        .limit(50)
    )
    if q:
        statement = statement.where(V1Memory.content.ilike(f"%{q}%"))
    return list(db.scalars(statement))


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: UUID, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    row = db.scalar(
        select(V1Memory).where(
            V1Memory.id == memory_id,
            V1Memory.user_id == UUID(user_id),
            V1Memory.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "Memory not found"})
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(memory_id: UUID, payload: MemoryUpdate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    row = db.scalar(select(V1Memory).where(V1Memory.id == memory_id, V1Memory.user_id == UUID(user_id)))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "Memory not found"})
    row.content = payload.content
    row.category = payload.category
    if payload.confidence is not None:
        row.confidence = payload.confidence
    if payload.approval_status is not None:
        if payload.approval_status == "approved" and not payload.consent:
            raise HTTPException(
                status_code=400,
                detail={"code": "memory_consent_required", "message": "Memory consent is required"},
            )
        row.approval_status = payload.approval_status
    db.commit()
    db.refresh(row)
    return row
