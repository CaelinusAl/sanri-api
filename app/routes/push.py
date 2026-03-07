from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.daily_intuition_service import generate_daily_notification

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/daily/{user_id}")
def daily_push(user_id: int, db: Session = Depends(get_db)):

    result = generate_daily_notification(db, user_id)

    return result