import random
from sqlalchemy.orm import Session

from app.services.memory import get_user_memory
from app.services.intuition_engine import detect_intuition_signal
from app.services.consciousness_engine import detect_consciousness


def build_daily_message(signal: str, consciousness: str):

    if signal == "fear":
        return "Bugün zihnin seni korumaya çalışıyor. Ama bazen güvenmek gerekir."

    if signal == "uncertainty":
        return "Bugün cevap arama. Sadece gözlemle."

    if signal == "longing":
        return "Bugün kalbin sana bir şey hatırlatmak istiyor."

    if signal == "readiness":
        return "Bugün küçük bir adım büyük bir kapı açabilir."

    if consciousness == "awakening":
        return "Bugün gördüğün işaretlere dikkat et."

    return random.choice([
        "Bugün bir şey sana anlamını gösterebilir.",
        "Bugün sezgine güven.",
        "Bugün bir soru seni ilerletebilir."
    ])


def generate_daily_notification(db: Session, user_id: int):

    memory = get_user_memory(db, user_id)

    signal = detect_intuition_signal(memory)

    consciousness = detect_consciousness(memory)

    message = build_daily_message(signal, consciousness)

    return {
        "signal": signal,
        "consciousness": consciousness,
        "message": message
    }