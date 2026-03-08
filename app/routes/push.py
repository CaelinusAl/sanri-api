from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.daily_intuition_service import generate_daily_notification
from app.services.memory import get_user_memory

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/daily")
def daily_push(user_id: int, db: Session = Depends(get_db)):

    memory = get_user_memory(db, user_id)

    data = generate_daily_notification(memory)

    return data