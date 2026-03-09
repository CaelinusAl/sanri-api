from fastapi import APIRouter, Request
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Any
import re

router = APIRouter(prefix="/global-signal", tags=["global-signal"])

GLOBAL_SIGNALS: List[Dict[str, Any]] = []


class SignalIn(BaseModel):
    text: str


def detect_country_from_request(request: Request) -> str:
    cf_country = request.headers.get("cf-ipcountry")
    if cf_country and cf_country != "XX":
        return cf_country.upper()

    accept_language = (request.headers.get("accept-language") or "").lower()

    if "tr" in accept_language:
        return "TR"
    if "en" in accept_language:
        return "EN"

    return "UNKNOWN"


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\sçğıöşü]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return [w for w in normalize_text(text).split(" ") if w]


def similarity_score(a: str, b: str) -> float:
    ta = set(tokenize(a))
    tb = set(tokenize(b))

    if not ta or not tb:
        return 0.0

    overlap = ta.intersection(tb)
    return len(overlap) / max(len(ta), len(tb))


def find_echo_matches(text: str, signals: list[dict], limit: int = 3):
    ranked = []

    for item in signals:
        other_text = item.get("text") or ""
        score = similarity_score(text, other_text)

        if score >= 0.25:
            ranked.append(
                {
                    "country": item.get("country") or "UNKNOWN",
                    "text": other_text,
                    "score": round(score, 3),
                }
            )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


@router.post("/send")
def send_global_signal(payload: SignalIn, request: Request):
    text = (payload.text or "").strip()

    if not text:
        return {
            "ok": False,
            "error": "EMPTY_SIGNAL"
        }

    # önce echo ara
    matches = find_echo_matches(text, GLOBAL_SIGNALS)

    signal = {
        "id": len(GLOBAL_SIGNALS) + 1,
        "text": text,
        "country": detect_country_from_request(request),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    # sonra akışa ekle
    GLOBAL_SIGNALS.insert(0, signal)

    return {
        "ok": True,
        "message": "Signal received.",
        "signal": signal,
        "echo": {
            "matched": len(matches) > 0,
            "items": matches
        }
    }


@router.get("/stream")
def get_global_stream():
    return {
        "ok": True,
        "signals": GLOBAL_SIGNALS[:100]
    }