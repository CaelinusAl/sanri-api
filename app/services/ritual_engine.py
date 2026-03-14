from typing import Dict


INTENT_RULES = {
    "release": ["bırak", "ağırlık", "yük", "sıkış", "özgürleş"],
    "love": ["aşk", "kalp", "sevgi", "ilişki", "özlem"],
    "fear": ["korku", "endişe", "panik", "kaygı"],
    "clarity": ["netlik", "karar", "yol", "anlam", "bulanık"],
    "abundance": ["para", "bolluk", "bereket", "akış", "kazanç"],
    "protection": ["korun", "nazar", "alan", "güven", "saldırı"],
}


def detect_intent(text: str) -> str:
    raw = (text or "").lower()

    for intent, words in INTENT_RULES.items():
        for w in words:
            if w in raw:
                return intent

    return "clarity"


def build_ritual(intent: str, transcript: str, lang: str = "tr") -> Dict:
    if lang != "tr":
        lang = "tr"

    if intent == "release":
        return {
            "ok": True,
            "intent": intent,
            "title": "Bırakma Ritüeli",
            "message": "Şimdi bedenindeki taşıdığın yükü fark et. Onunla savaşma. Sadece gör.",
            "steps": [
                "Gözlerini kapat ve omuzlarını gevşet.",
                "4 sayıda nefes al, 6 sayıda ver.",
                "İçindeki ağırlığı bir renk ya da şekil gibi hayal et.",
                "Her nefes verişte bu yükün bedeninden aşağı aktığını hisset.",
                "Son nefeste 'Bunu artık taşımıyorum' de."
            ],
            "closing": "Bugün senden çıkan şey artık sana ait değil.",
        }

    if intent == "love":
        return {
            "ok": True,
            "intent": intent,
            "title": "Kalp Açılım Ritüeli",
            "message": "Kalbini zorla açma. Sadece etrafındaki duvarı fark et.",
            "steps": [
                "Sağ elini kalbine koy.",
                "3 derin nefes al.",
                "Kalbinin etrafındaki sert alanı hisset.",
                "Nefes verirken göğsünde yumuşama hayal et.",
                "İçinden 'Sevgi güvenle bende açılır' de."
            ],
            "closing": "Kalp açılımı zorlanmaz; hatırlanır.",
        }

    if intent == "fear":
        return {
            "ok": True,
            "intent": intent,
            "title": "Korku Çözme Ritüeli",
            "message": "Korku düşman değil; bedende donmuş bir alarmdır.",
            "steps": [
                "Ayak tabanlarını yere bastır.",
                "Bulunduğun yerde 3 nesneye bak.",
                "Nefes alırken 'buradayım', verirken 'güvendeyim' de.",
                "Korkunun bedendeki yerini bul.",
                "Oraya sıcak bir ışık gönderdiğini hayal et."
            ],
            "closing": "Beden gördüğünde sakinleşir.",
        }

    if intent == "abundance":
        return {
            "ok": True,
            "intent": intent,
            "title": "Akış ve Bolluk Ritüeli",
            "message": "Bolluk önce izin alanında açılır.",
            "steps": [
                "Omurganı dikleştir.",
                "Kollarını hafifçe aç.",
                "Nefes alırken başının üstünden ışık indiğini hayal et.",
                "Nefes verirken bu ışığın kalbine ve karnına dolduğunu hisset.",
                "İçinden 'Akış bana güvenle gelir' de."
            ],
            "closing": "Bolluk önce frekansta, sonra maddede görünür.",
        }

    if intent == "protection":
        return {
            "ok": True,
            "intent": intent,
            "title": "Alan Koruma Ritüeli",
            "message": "Önce alanını hisset, sonra sınırını belirle.",
            "steps": [
                "Gözlerini kapat.",
                "Bedeninin etrafında 1 metre çapında bir ışık alanı hayal et.",
                "Bu alanın dışına ait olmayan her şeyi geri gönderdiğini hisset.",
                "İçinden 'Alanım bana aittir' de.",
                "Son nefeste omuzlarını bırak."
            ],
            "closing": "Koruma korkudan değil, merkezden doğar.",
        }

    return {
        "ok": True,
        "intent": "clarity",
        "title": "Netlik Ritüeli",
        "message": "Bulanıklığı hemen çözmeye çalışma. Önce merkezini bul.",
        "steps": [
            "Bir elini kalbine, bir elini karnına koy.",
            "3 derin nefes al.",
            "Aklındaki soruyu tek cümleye indir.",
            "O cümleyi sessizce içinden tekrar et.",
            "İlk gelen hissi not et."
        ],
        "closing": "Netlik bazen cevap değil, doğru hissin kendisidir.",
    }