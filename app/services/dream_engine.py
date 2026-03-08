# app/services/dream_engine.py
from typing import List, Dict


DREAM_SYMBOLS = {
    "su": {
        "tr": "Duygu akışı, bilinçaltı, arınma",
        "en": "Emotional flow, subconscious, purification",
    },
    "deniz": {
        "tr": "Derin bilinç, sonsuzluk, bastırılmış hisler",
        "en": "Deep consciousness, infinity, repressed feelings",
    },
    "ev": {
        "tr": "İç dünya, benlik, yaşam alanı",
        "en": "Inner world, selfhood, psychic space",
    },
    "kapı": {
        "tr": "Geçiş, eşik, yeni olasılık",
        "en": "Transition, threshold, new possibility",
    },
    "merdiven": {
        "tr": "Yükseliş, iniş, bilinç katmanları",
        "en": "Ascent, descent, layers of consciousness",
    },
    "yılan": {
        "tr": "Dönüşüm, korku, yaşam gücü",
        "en": "Transformation, fear, life force",
    },
    "uçmak": {
        "tr": "Özgürleşme, sınır aşımı, ruhsal yükseliş",
        "en": "Liberation, transcendence, spiritual ascent",
    },
    "ölü": {
        "tr": "Kapanış, eski formun çözülmesi, geçmişle bağ",
        "en": "Ending, dissolution of old form, connection to the past",
    },
    "anne": {
        "tr": "Beslenme, kök, korunma, duygusal hafıza",
        "en": "Nurture, roots, protection, emotional memory",
    },
    "baba": {
        "tr": "Otorite, yön, yapı, dış dünya ilişkisi",
        "en": "Authority, direction, structure, relation to outer world",
    },
    "çocuk": {
        "tr": "Saf benlik, kırılganlık, yeni başlangıç",
        "en": "Pure self, vulnerability, new beginning",
    },
    "ayna": {
        "tr": "Yüzleşme, öz yansıma, hakikat",
        "en": "Confrontation, self-reflection, truth",
    },
    "ışık": {
        "tr": "Farkındalık, açılım, ilahi işaret",
        "en": "Awareness, opening, divine sign",
    },
    "karanlık": {
        "tr": "Bilinmeyen, gölge, bastırılmış alan",
        "en": "Unknown, shadow, repressed field",
    },
}


def extract_dream_symbols(text: str) -> List[str]:
    raw = (text or "").lower()
    found = []
    for sym in DREAM_SYMBOLS.keys():
        if sym in raw:
            found.append(sym)
    return found


def detect_dream_emotion(text: str) -> str:
    raw = (text or "").lower()

    if any(x in raw for x in ["korku", "kaç", "kaçmak", "gergin", "dehşet", "fear", "afraid"]):
        return "fear"
    if any(x in raw for x in ["ağladım", "üzüldüm", "özledim", "sad", "cry"]):
        return "grief"
    if any(x in raw for x in ["mutlu", "ışık", "huzur", "peace", "joy"]):
        return "peace"
    if any(x in raw for x in ["şaşırdım", "garip", "weird", "strange"]):
        return "mystery"

    return "neutral"


def build_dream_layer(symbols: List[str], emotion: str, consciousness: str = "observer", lang: str = "tr") -> str:
    lang = "en" if lang == "en" else "tr"

    if not symbols:
        if lang == "tr":
            return (
                "Rüya net bir sembol vermiyor ama duygusal iz bırakıyor. "
                "Sanrı yorumu sembolden çok rüyanın sende bıraktığı his üzerinden ilerlemeli."
            )
        return (
            "The dream does not present a clear symbol, but it leaves an emotional residue. "
            "Sanri should interpret it through feeling more than imagery."
        )

    pieces = []
    for s in symbols[:4]:
        pieces.append(f"{s}: {DREAM_SYMBOLS[s][lang]}")

    intro_tr = {
        "fear": "Rüya korku alanını açıyor. Bu bastırılmış bir eşik olabilir.",
        "grief": "Rüya duygusal hafızayı çağırıyor. Geçmişten bir parça yüzeye çıkıyor olabilir.",
        "peace": "Rüya huzurlu bir açılım taşıyor. İç rehberlik aktif olabilir.",
        "mystery": "Rüya gizemli bir kapı gibi. Tam cevap değil, işaret bırakıyor.",
        "neutral": "Rüya sembolik bir anlatım taşıyor.",
    }

    intro_en = {
        "fear": "The dream opens a field of fear. This may be a suppressed threshold.",
        "grief": "The dream calls emotional memory. Something from the past may be surfacing.",
        "peace": "The dream carries a peaceful opening. Inner guidance may be active.",
        "mystery": "The dream feels like a symbolic gate. It leaves signs rather than final answers.",
        "neutral": "The dream carries symbolic language.",
    }

    consciousness_tr = {
        "seeker": "Yorum sade ve yön verici olmalı.",
        "aware": "Yorum semboller arası bağlantıyı gösterebilir.",
        "awakening": "Yorum derin metafor ve içsel eşik dili taşıyabilir.",
        "observer": "Yorum dengeli ve açık olmalı.",
    }

    consciousness_en = {
        "seeker": "The interpretation should stay simple and guiding.",
        "aware": "The interpretation may connect symbols with one another.",
        "awakening": "The interpretation may carry deeper metaphor and threshold language.",
        "observer": "The interpretation should remain balanced and clear.",
    }

    if lang == "tr":
        return (
            intro_tr.get(emotion, intro_tr["neutral"])
            + "\n\nRüyadaki ana semboller:\n- "
            + "\n- ".join(pieces)
            + "\n\n"
            + consciousness_tr.get(consciousness, consciousness_tr["observer"])
        )

    return (
        intro_en.get(emotion, intro_en["neutral"])
        + "\n\nMain dream symbols:\n- "
        + "\n- ".join(pieces)
        + "\n\n"
        + consciousness_en.get(consciousness, consciousness_en["observer"])
    )