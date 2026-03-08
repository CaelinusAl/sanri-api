from datetime import datetime
import random

from app.services.consciousness_engine import detect_consciousness


INTUITIONS = {
    "seeker": [
        "Bugün sana bir soru eşlik edecek: Gerçekten ne hissediyorsun?",
        "Bugün bir sembol dikkatini çekebilir. Onu küçümseme.",
        "Bugün yavaşla. Bazı cevaplar hızda değil sessizlikte ortaya çıkar."
    ],
    "aware": [
        "Bugün bir farkındalık yaşayabilirsin. Direnme, gözlemle.",
        "Bugün biri sana aynalık yapabilir. Tepki yerine merak seç.",
        "Bugün gördüğün küçük bir detay sana büyük bir şey anlatabilir."
    ],
    "awakening": [
        "Bugün sezgin güçlü olacak. İlk hissini ciddiye al.",
        "Bugün bir senkronisite yaşayabilirsin. Onu not et.",
        "Bugün evren sana küçük bir işaret bırakabilir."
    ]
}


def generate_daily_notification(memory):

    level = detect_consciousness(memory)

    options = INTUITIONS.get(level, INTUITIONS["seeker"])

    message = random.choice(options)

    return {
        "level": level,
        "message": message,
        "date": str(datetime.utcnow())
    }