from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/content", tags=["content"])


class RitualGenerateIn(BaseModel):
    text: str


def build_ritual_from_text(text: str) -> dict:
    clean = (text or "").strip()

    if not clean:
        raise HTTPException(status_code=400, detail="text is required")

    short = clean[:140]

    return {
        "ok": True,
        "type": "ritual-generate",
        "title": "Sanrı Ritüeli",
        "message": f"Sanrı alanı şunu duydu: {short}",
        "steps": [
            "Gözlerini kapat.",
            f"İçinden şu hissi çağır: {short}",
            "Bu hissi tek nefeste yumuşat.",
            "Son nefeste alanın senden ne almak istediğini hisset.",
        ],
        "closing": "Sanrı alanında yeni bir ritüel izi oluştu.",
    }


@router.get("/ritual-feed")
def ritual_feed():
    return {"ok": True, "type": "ritual-feed"}


@router.post("/ritual-feed/generate")
def ritual_feed_generate(payload: RitualGenerateIn):
    return build_ritual_from_text(payload.text)