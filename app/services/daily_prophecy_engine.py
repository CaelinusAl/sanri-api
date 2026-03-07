from typing import List, Dict, Any


def predict_daily_state(user_memory: List[Dict] | None, insight: Dict | None) -> str:

    memory = user_memory or []

    text = " ".join([
        (m.get("input_text") or "")
        for m in memory
    ]).lower()

    if "korku" in text or "fear" in text or "endişe" in text:
        return "shadow"

    if "neden" in text or "why" in text or "anlam" in text:
        return "reflection"

    if "yoruldum" in text or "yorgun" in text:
        return "silence"

    if "yeni" in text or "değişim" in text:
        return "awakening"

    if "yarat" in text or "üret" in text:
        return "creation"

    if insight:
        pattern = str(insight.get("pattern") or "").lower()
        if "creator" in pattern:
            return "creation"

    return "focus"



def build_daily_prophecy(state: str, lang: str = "tr", name: str | None = None):

    prefix = f"{name}, " if name else ""

    bank = {

        "focus": {
            "tr": prefix + "Bugün odak günün. Gürültüyü azalt ve küçük işaretleri kaçırma.",
            "en": prefix + "Today is your focus day. Reduce noise and notice subtle signs."
        },

        "shadow": {
            "tr": prefix + "Bugün gölge görünmek isteyebilir. Kaçma, sadece fark et.",
            "en": prefix + "Your shadow may want to appear today. Do not escape, just observe."
        },

        "reflection": {
            "tr": prefix + "Bugün cevap değil anlam günü.",
            "en": prefix + "Today is not for answers, but meaning."
        },

        "silence": {
            "tr": prefix + "Bugün yavaşla. Sessizlik senden daha çok şey biliyor.",
            "en": prefix + "Slow down today. Silence knows more than urgency."
        },

        "awakening": {
            "tr": prefix + "Bugün yeni bir fark ediş açılıyor.",
            "en": prefix + "A new awareness opens today."
        },

        "creation": {
            "tr": prefix + "Bugün yaratım enerjin açık.",
            "en": prefix + "Your creative energy is open today."
        }

    }

    lang = "en" if lang == "en" else "tr"

    return bank.get(state, bank["focus"])[lang]