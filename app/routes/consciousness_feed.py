from fastapi import APIRouter
from app.services.consciousness_feed import generate_feed

router = APIRouter(prefix="/content", tags=["content"])

@router.get("/system-feed")
def system_feed(lang: str = "tr"):
    return generate_feed(lang)