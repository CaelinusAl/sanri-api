"""FAZ 2 — Yaşam teması sınıflandırıcı.

Strateji: kullanıcı sorularını kategorize et (aşk, ayrılık, rüya, kaygı,
kararsızlık, hayat amacı, para, aile, yalnızlık, öz değer).

Keyword tabanlı, deterministik ve maliyetsiz — her mesajda LLM çağırmadan
çalışır. Türkçe büyük/küçük harf ve yaygın çekimler gözetilir.
"""

from __future__ import annotations

import unicodedata

# Tema anahtarları + kullanıcıya gösterilecek etiketler.
THEME_LABELS = {
    "ask": "Aşk",
    "ayrilik": "Ayrılık",
    "ruya": "Rüya",
    "kaygi": "Kaygı",
    "kararsizlik": "Kararsızlık",
    "hayat_amaci": "Hayat Amacı",
    "para": "Para",
    "aile": "Aile",
    "yalnizlik": "Yalnızlık",
    "ozdeger": "Öz Değer",
    "diger": "Diğer",
}

# Her tema için anahtar kelime/kök listesi (normalize edilmiş: küçük harf, aksansız).
# Eşleşme alt-dize bazlıdır; bu yüzden kökler çekimleri de yakalar (örn. "ayril").
_THEME_KEYWORDS = {
    "ayrilik": [
        "ayril", "terk et", "terk etti", "bosan", "bosand", "bitti iliski",
        "eski sevgili", "aldat", "ihanet", "ayrildik", "ayrilma", "bitirdik",
    ],
    "ask": [
        "ask", "asik", "sevgili", "seviyorum", "flort", "romantik", "kalbim",
        "begeniyorum", "crush", "tutuldum", "hoslan", "iliskiye basla",
    ],
    "ruya": [
        "ruya", "ruyam", "kabus", "ruyada", "ruyamda", "dus gordum", "ruya gordum",
    ],
    "kaygi": [
        "kaygi", "endise", "panik", "stres", "anksiyete", "huzursuz", "gergin",
        "korkuyorum", "tedirgin", "icim sikis", "nefes alam", "kotu hissed",
    ],
    "kararsizlik": [
        "karar veremiyor", "kararsiz", "ne yapmaliyim", "ne yapsam", "ikilem",
        "emin degilim", "teredd", "secim yap", "hangisini", "kafam karisik",
    ],
    "hayat_amaci": [
        "hayatin anlami", "yasam amaci", "amacim ne", "neden buradayim",
        "anlamsiz", "bosluk hissed", "hiclik", "hedefim", "ne istedigimi bilmiyor",
        "yolumu", "varolus",
    ],
    "para": [
        "para", "borc", "maddi", "maas", "ekonomik", "is bulamiyor", "issiz",
        "fatura", "kira", "fakir", "zengin", "butce", "gelir",
    ],
    "aile": [
        "annem", "babam", "kardes", "ailem", "esim", "cocugum", "akraba",
        "anne", "baba", "kayinvalide", "aile ici", "evlilik",
    ],
    "yalnizlik": [
        "yalniz", "kimsem yok", "yapayalniz", "kimse anlamiyor", "kimsesiz",
        "dislanm", "izole", "tek basima", "arkadasim yok",
    ],
    "ozdeger": [
        "degersiz", "yetersiz", "ozguven", "ozsayg", "kendimi sevmiyor",
        "basarisiz hissed", "kendimi begenmiyor", "ise yaramaz", "kotuyum",
        "kendime guven",
    ],
}


def _normalize(text: str) -> str:
    """Küçük harf + Türkçe aksanları sadeleştir (ı/İ/ş/ç/ğ/ö/ü → ascii yakını)."""
    t = (text or "").lower()
    # Türkçe'ye özgü dönüşümler (unicodedata bazılarını kaçırır).
    repl = {"ı": "i", "İ": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u", "â": "a", "î": "i", "û": "u"}
    for a, b in repl.items():
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t


def classify_theme(message: str) -> str:
    """Mesajı tek bir baskın temaya eşler. Eşleşme yoksa 'diger'."""
    norm = _normalize(message)
    if not norm.strip():
        return "diger"

    scores: dict[str, int] = {}
    for theme, keywords in _THEME_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in norm)
        if hits:
            scores[theme] = hits

    if not scores:
        return "diger"

    # En yüksek skor; eşitlikte sabit öncelik sırası (ayrılık > aşk > ... ).
    priority = list(_THEME_KEYWORDS.keys())
    best = max(scores.items(), key=lambda kv: (kv[1], -priority.index(kv[0])))
    return best[0]


def theme_label(theme: str) -> str:
    return THEME_LABELS.get(theme, THEME_LABELS["diger"])
