# app/routes/dream.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.memory import get_user_memory
from app.services.sanri_consciousness_engine import detect_consciousness
from app.services.dream_engine import (
    extract_dream_symbols,
    detect_dream_emotion,
    build_dream_layer,
)

router = APIRouter(prefix="/dream", tags=["dream"])


class DreamIn(BaseModel):
    user_id: int
    text: str
    lang: str | None = "tr"


@router.post("/interpret")
def interpret_dream(payload: DreamIn, db: Session = Depends(get_db)):
    memory = get_user_memory(db, payload.user_id)
    consciousness = detect_consciousness(memory)

    symbols = extract_dream_symbols(payload.text)
    emotion = detect_dream_emotion(payload.text)
    interpretation = build_dream_layer(
        symbols=symbols,
        emotion=emotion,
        consciousness=consciousness,
        lang=payload.lang or "tr",
    )

    return {
        "symbols": symbols,
        "emotion": emotion,
        "consciousness": consciousness,
        "interpretation": interpretation,
    }