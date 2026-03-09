from fastapi import APIRouter, Request
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Any

router = APIRouter(prefix="/global-signal", tags=["global-signal"])

GLOBAL_SIGNALS: List[Dict[str, Any]] = []


class SignalIn(BaseModel):
    text: str


def detect_country_from_request(request: Request) -> str:
    cf_country = request.headers.get("cf-ipcountry")
    if cf_country and cf_country != "XX":
        return cf_country

    accept_language = (request.headers.get("accept-language") or "").lower()

    if "tr" in accept_language:
        return "TR"
    if "en" in accept_language:
        return "EN"

    return "UNKNOWN"


@router.post("/send")
def send_global_signal(payload: SignalIn, request: Request):
    text = (payload.text or "").strip()

    if not text:
        return {
            "ok": False,
            "error": "EMPTY_SIGNAL"
        }

    signal = {
        "id": len(GLOBAL_SIGNALS) + 1,
        "text": text,
        "country": detect_country_from_request(request),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    GLOBAL_SIGNALS.insert(0, signal)

    return {
        "ok": True,
        "message": "Signal received.",
        "signal": signal
    }


@router.get("/stream")
def get_global_stream():
    return {
        "ok": True,
        "signals": GLOBAL_SIGNALS[:100]
    }