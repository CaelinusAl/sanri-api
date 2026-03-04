import random
from datetime import datetime

SYMBOLS = [
    "Kapı",
    "Ayna",
    "Köprü",
    "Anahtar",
    "Spiral",
    "Ateş",
]

SIGNALS = [
    "Sistem yön değiştiriyor.",
    "Yeni bir bilinç kapısı açılıyor.",
    "Eski döngü kapanıyor.",
    "Enerji yeniden yazılıyor.",
]

MESSAGES = [
    "Gördüğün her şey bir işaret.",
    "Bugün karar vermek için doğru gün.",
    "Korku bir eşiktir.",
]

ACTIONS = [
    "Bir şey başlat.",
    "Bir şeyi bitir.",
    "Birine mesaj gönder.",
    "Sessizlikte kal.",
]


def generate_feed(lang="tr"):
    return {
        "date": datetime.utcnow().isoformat(),
        "signal": random.choice(SIGNALS),
        "symbol": random.choice(SYMBOLS),
        "message": random.choice(MESSAGES),
        "action": random.choice(ACTIONS),
        "share": "Sanrı System Feed",
    }