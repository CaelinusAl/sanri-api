from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db import get_db
from app.models.v1 import V1Memory
from app.schemas.v1 import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_service import create_memory


router = APIRouter(prefix="/v1/memories", tags=["v1-memories"])


@router.post("", response_model=MemoryResponse, status_code=201)
def save_memory(payload: MemoryCreate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    if not payload.consent:
        raise HTTPException(status_code=400, detail={"code": "memory_consent_required", "message": "Memory consent is required"})
    return create_memory(db, user_id, payload.content, payload.memory_type)


@router.get("/search", response_model=list[MemoryResponse])
def search_memories(
    q: str | None = Query(default=None, max_length=200),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    statement = select(V1Memory).where(V1Memory.user_id == UUID(user_id)).order_by(V1Memory.created_at.desc()).limit(50)
    if q:
        statement = statement.where(V1Memory.content.ilike(f"%{q}%"))
    return list(db.scalars(statement))


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: UUID, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    result = db.execute(delete(V1Memory).where(V1Memory.id == memory_id, V1Memory.user_id == UUID(user_id)))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "Memory not found"})
    db.commit()


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(memory_id: UUID, payload: MemoryUpdate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    row = db.scalar(select(V1Memory).where(V1Memory.id == memory_id, V1Memory.user_id == UUID(user_id)))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "memory_not_found", "message": "Memory not found"})
    row.content = payload.content
    db.commit()
    db.refresh(row)
    return row
