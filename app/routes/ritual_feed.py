from fastapi import APIRouter

router = APIRouter(prefix="/content", tags=["content"])

@router.get("/ritual-feed")
def ritual_feed():
    return {"ok": True, "type": "ritual-feed"}

@router.get("/ritual-feed/generate")
def ritual_feed_generate():
    return {"ok": True, "type": "ritual-generate"}