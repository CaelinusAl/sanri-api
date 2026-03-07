# app/services/consciousness_engine.py

from datetime import date
import random

SYMBOLS = [
    {
        "title_tr": "Altın Oran",
        "title_en": "Golden Ratio",
        "text_tr": "Kaos sandığın şey düzenin görünmeyen halidir.",
        "text_en": "What you call chaos is hidden order."
    },
    {
        "title_tr": "Ayna",
        "title_en": "Mirror",
        "text_tr": "Karşına çıkan kişi senin yansımandır.",
        "text_en": "The person you meet is your reflection."
    },
    {
        "title_tr": "Kapı",
        "title_en": "Gate",
        "text_tr": "Bazı kapılar soruyla açılır.",
        "text_en": "Some doors open with questions."
    }
]

QUESTIONS = [
    {
        "tr": "Bugün seni en çok hangi şey tetikledi?",
        "en": "What triggered you most today?"
    },
    {
        "tr": "Bugün hangi sembol sana tekrar tekrar göründü?",
        "en": "What symbol appeared repeatedly today?"
    }
]

RITUALS = [
    {
        "tr": "Gözlerini kapat ve 3 nefes al.",
        "en": "Close your eyes and take 3 breaths."
    },
    {
        "tr": "Bugün bir şeyi yargılamadan izle.",
        "en": "Observe something today without judging."
    }
]


def generate_daily_feed(lang="tr"):
    today = date.today().isoformat()

    symbol = random.choice(SYMBOLS)
    question = random.choice(QUESTIONS)
    ritual = random.choice(RITUALS)

    return {
        "date": today,
        "symbol": {
            "title": symbol["title_tr"] if lang == "tr" else symbol["title_en"],
            "text": symbol["text_tr"] if lang == "tr" else symbol["text_en"]
        },
        "question": question["tr"] if lang == "tr" else question["en"],
        "ritual": ritual["tr"] if lang == "tr" else ritual["en"]
    }
    
def detect_consciousness(memory):
    """
    Basit bilinç seviyesi tahmini
    """
    if not memory:
        return "seeker"

    score = len(memory)

    if score > 15:
        return "awakening"
    elif score > 6:
        return "aware"
    else:
        return "seeker"