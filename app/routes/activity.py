from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.legacy_identity import reject_unsafe_legacy_identity
from app.db import get_db

router = APIRouter()


class MemoryIn(BaseModel):
    user_id: int
    type: str
    content: str


@router.get("/memory/{user_id}")
def get_memory(user_id: int, db: Session = Depends(get_db)):
    del user_id, db
    reject_unsafe_legacy_identity()


@router.post("/memory")
def save_memory(payload: MemoryIn, db: Session = Depends(get_db)):
    del payload, db
    reject_unsafe_legacy_identity()