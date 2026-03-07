# app/services/pulse_engine.py
from typing import Any


def predict_daily_state(user_memory: list[dict] | None, insight: dict | None) -> str:
    memory = user_memory or []
    text = " ".join([(m.get("input_text") or "") for m in memory]).lower()

    if "korku" in text or "fear" in text or "endişe" in text:
        return "shadow"

    if "neden" in text or "why" in text or "anlam" in text:
        return "reflection"

    if "yorgun" in text or "yoruldum" in text or "tired" in text:
        return "silence"

    if "değişim" in text or "change" in text or "yeni" in text:
        return "awakening"

    if insight and isinstance(insight, dict):
        pat = str(insight.get("pattern") or "").lower()
        if "creator" in pat:
            return "focus"

    return "focus"


def build_daily_message(state: str, lang: str = "tr") -> str:
    bank = {
        "focus": {
            "tr": "Bugün odak günün. Gürültüyü azalt, işaretleri dinle.",
            "en": "Today is a focus day. Reduce the noise and listen to the signs.",
        },
        "shadow": {
            "tr": "Bugün gölge kendini gösterebilir. Kaçma, sadece fark et.",
            "en": "Your shadow may show itself today. Do not escape, simply notice it.",
        },
        "awakening": {
            "tr": "Bugün yeni bir fark ediş açılıyor. Küçük olana dikkat et.",
            "en": "A new awareness opens today. Pay attention to the small things.",
        },
        "reflection": {
            "tr": "Bugün cevap değil, anlam günü. Bir cümle sana yön verecek.",
            "en": "Today is not for answers, but meaning. One sentence will guide you.",
        },
        "silence": {
            "tr": "Bugün yavaşla. Sessizlik, senden daha çok şey biliyor.",
            "en": "Slow down today. Silence knows more than urgency.",
        },
    }
    lang = "en" if (lang or "").lower() == "en" else "tr"
    return bank.get(state, bank["focus"])[lang]