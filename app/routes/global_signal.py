from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/global", tags=["global"])

# geçici hafıza (DB yerine)
GLOBAL_SIGNALS = []

class SignalRequest(BaseModel):
    text: str
    country: str = "unknown"


@router.post("/send")
def send_signal(req: SignalRequest):

    signal = {
        "text": req.text.strip(),
        "country": req.country,
        "created_at": datetime.utcnow().isoformat()
    }

    GLOBAL_SIGNALS.insert(0, signal)

    return {
        "ok": True,
        "message": "Signal received."
    }


@router.get("/stream")
def get_stream():

    return {
        "signals": GLOBAL_SIGNALS[:50]
    }