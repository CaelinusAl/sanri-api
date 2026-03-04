from fastapi import APIRouter
from app.services.consciousness_engine import generate_daily_feed

router = APIRouter(prefix="/consciousness", tags=["consciousness"])


@router.get("/daily")
def get_daily(lang: str = "tr"):
    return generate_daily_feed(lang)