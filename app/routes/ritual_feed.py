from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.ritual_feed import latest_ritual, generate_ritual

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/ritual-feed")
def ritual_feed(db: Session = Depends(get_db)):
    return latest_ritual(db)


@router.get("/ritual-feed/generate")
def ritual_generate(db: Session = Depends(get_db)):
    return generate_ritual(db)