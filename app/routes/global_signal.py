from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Dict, Any
import re

router = APIRouter(prefix="/global-signal", tags=["global-signal"])

GLOBAL_SIGNALS: List[Dict[str, Any]] = []
GLOBAL_NOTIFICATIONS: List[Dict[str, Any]] = []

MAX_SIGNALS = 5000
MAX_NOTIFICATIONS = 2000
ECHO_DELAY_MINUTES = 10


class SignalIn(BaseModel):
    text: str
    user_id: str = "anonymous"


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


def find_echo_matches_for_signal(base_signal: dict, signals: list[dict], limit: int = 3):
    ranked = []
    base_id = base_signal.get("id")
    base_text = base_signal.get("text") or ""

    for item in signals:
        if item.get("id") == base_id:
            continue

        other_text = item.get("text") or ""
        score = similarity_score(base_text, other_text)

        if score >= 0.25:
            ranked.append(
                {
                    "signal_id": item.get("id"),
                    "country": item.get("country") or "UNKNOWN",
                    "text": other_text,
                    "score": round(score, 3),
                }
            )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


def utc_now() -> datetime:
    return datetime.utcnow()


def parse_iso_z(value: str) -> datetime:
    value = (value or "").replace("Z", "")
    return datetime.fromisoformat(value)


def already_notified(signal_id: int) -> bool:
    return any(n.get("signal_id") == signal_id for n in GLOBAL_NOTIFICATIONS)


@router.post("/send")
def send_global_signal(payload: SignalIn, request: Request):
    text = (payload.text or "").strip()
    user_id = (payload.user_id or "anonymous").strip()

    if not text:
        return {
            "ok": False,
            "error": "EMPTY_SIGNAL"
        }

    signal = {
        "id": len(GLOBAL_SIGNALS) + 1,
        "user_id": user_id,
        "text": text,
        "country": detect_country_from_request(request),
        "created_at": utc_now().isoformat() + "Z",
        "echo_processed": False,
    }

    GLOBAL_SIGNALS.insert(0, signal)
    if len(GLOBAL_SIGNALS) > MAX_SIGNALS:
        GLOBAL_SIGNALS[:] = GLOBAL_SIGNALS[:MAX_SIGNALS]

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


@router.post("/process-echoes")
def process_echoes(force: bool = Query(default=False)):
    now = utc_now()
    created_notifications = []

    # oldest-first işle
    for signal in sorted(GLOBAL_SIGNALS, key=lambda x: x["id"]):
        if signal.get("echo_processed"):
            continue

        created_at = parse_iso_z(signal["created_at"])
        age_ok = now - created_at >= timedelta(minutes=ECHO_DELAY_MINUTES)

        if not age_ok and not force:
            continue

        matches = find_echo_matches_for_signal(signal, GLOBAL_SIGNALS)

        signal["echo_processed"] = True
        signal["echo_matches"] = matches

        if matches and not already_notified(signal["id"]):
            notification = {
                "id": len(GLOBAL_NOTIFICATIONS) + 1,
                "user_id": signal["user_id"],
                "signal_id": signal["id"],
                "title": "Your signal echoed.",
                "message": "Alanın başka yerlerinde benzer hisler belirdi.",
                "items": matches,
                "created_at": utc_now().isoformat() + "Z",
                "is_read": False,
            }
            GLOBAL_NOTIFICATIONS.insert(0, notification)
            if len(GLOBAL_NOTIFICATIONS) > MAX_NOTIFICATIONS:
                GLOBAL_NOTIFICATIONS[:] = GLOBAL_NOTIFICATIONS[:MAX_NOTIFICATIONS]
            created_notifications.append(notification)

    return {
        "ok": True,
        "created": len(created_notifications),
        "notifications": created_notifications,
    }


@router.get("/notifications")
def get_notifications(user_id: str = Query(...)):
    items = [n for n in GLOBAL_NOTIFICATIONS if n.get("user_id") == user_id]
    return {
        "ok": True,
        "items": items[:20]
    }


@router.post("/notifications/read/{notification_id}")
def mark_notification_read(notification_id: int):
    for item in GLOBAL_NOTIFICATIONS:
        if item.get("id") == notification_id:
            item["is_read"] = True
            return {"ok": True}

    return {"ok": False, "error": "NOTIFICATION_NOT_FOUND"}