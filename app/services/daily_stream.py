# app/services/daily_stream.py
from datetime import date
import random

DAILY_TR = [
    {
        "kicker": "Günün Akışı",
        "title": "Frekansını hatırla",
        "text": "Bugün dış dünyaya değil iç sinyaline bak."
    },
    {
        "kicker": "Bilinç Mesajı",
        "title": "Sistem konuşuyor",
        "text": "Gördüğün tekrarlar rastgele değildir."
    },
]

DAILY_EN = [
    {
        "kicker": "Daily Flow",
        "title": "Remember your frequency",
        "text": "Look at your inner signal today."
    },
]

WEEKLY_TR = {
    "title": "Altın Oran – Işığa Dönen Merkez",
    "reading_tr": "Kaos sandığın şey düzenin görünmeyen halidir."
}

WEEKLY_EN = {
    "title": "Golden Ratio – Center of Light",
    "reading_en": "What you call chaos is hidden order."
}


def get_or_create_daily(db, lang="tr"):
    today = date.today().isoformat()

    pool = DAILY_TR if lang == "tr" else DAILY_EN
    item = random.choice(pool)

    return {
        "date": today,
        "kicker": item["kicker"],
        "title": item["title"],
        "text": item["text"]
    }


def get_or_create_weekly(db, lang="tr"):
    if lang == "tr":
        return WEEKLY_TR
    return WEEKLY_EN