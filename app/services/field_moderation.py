"""Spam / düşük kalite taraması — Anlaşılma→Yankı hissel akışı."""
from __future__ import annotations

import json
import os
import re
from typing import Literal

from openai import OpenAI

Kind = Literal["share", "echo"]


def _heuristic_block(text: str, kind: Kind) -> tuple[bool, str]:
    t = (text or "").strip()
    min_len = 12 if kind == "share" else 6
    if len(t) < min_len:
        return True, "Metin çok kısa; biraz daha aç."

    if len(t) > (500 if kind == "share" else 280):
        return True, "Metin çok uzun."

    url_n = len(re.findall(r"https?://|www\.", t, re.I))
    if url_n > 2:
        return True, "Çok fazla bağlantı."

    if re.search(r"(.)\1{12,}", t):
        return True, "Tekrarlayan karakter spamı."

    # Basit reklam kalıpları
    if re.search(
        r"(instagram\.com|tiktok\.com|telegram\.me|t\.me/|wa\.me|http[s]?://[^\s]+){3,}",
        t,
        re.I,
    ):
        return True, "Spam benzeri içerik."

    letters = [c for c in t if c.isalpha()]
    if letters:
        caps = sum(1 for c in letters if c.isupper())
        if len(letters) >= 20 and caps / len(letters) > 0.85:
            return True, "Daha sakin bir ton dene."

    return False, ""


def _client() -> OpenAI | None:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    return OpenAI(api_key=key)


def moderate_field_text(text: str, kind: Kind, frequency_hz: int | None = None) -> tuple[bool, str, str | None]:
    """
    Returns (allowed, user_message, energy_feel).
    energy_feel only filled for kind=='share' when AI runs.
    """
    blocked, reason = _heuristic_block(text, kind)
    if blocked:
        return False, reason, None

    client = _client()
    if not client:
        return True, "", "nötr bir titreşim" if kind == "share" else None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    if kind == "share":
        sys = """Sen içerik moderatörüsün. Türkçe kısa niyet metinlerini değerlendir.
Sadece geçerli JSON döndür (başka metin yok):
{"allow": true/false, "spam": true/false, "low_quality": true/false,
 "energy_feel": "2-5 kelime, hissel bir enerji tanımı (ör. yumuşak bir açıklık, keskin merak)",
 "reason_tr": "reddedildiyse kısa Türkçe sebep, yoksa boş string"}
spam: reklam, bağlantı istismarı, tekrar, anlamsız doldurma.
low_quality: tek kelime, anlamsız, nefret, şiddet teşviki, cinsel istismar."""
        user = f"Frekans: {frequency_hz or '?'} Hz\nMetin:\n{text.strip()[:600]}"
    else:
        sys = """Sen içerik moderatörüsün. Türkçe kısa "yankı" yanıtlarını değerlendir.
Sadece geçerli JSON döndür:
{"allow": true/false, "spam": true/false, "low_quality": true/false,
 "reason_tr": "reddedildiyse kısa Türkçe sebep, yoksa boş string"}
Yankı derin, kısa ve saygılı olmalı; hakaret, reklam, boş tekrar yasak."""
        user = f"Yankı metni:\n{text.strip()[:400]}"

    try:
        comp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=200,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        )
        raw = (comp.choices[0].message.content or "").strip()
        data = json.loads(raw) if raw.startswith("{") else {}
        if not data:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                data = json.loads(m.group(0))
        allow = bool(data.get("allow", True)) and not data.get("spam") and not data.get("low_quality")
        reason = (data.get("reason_tr") or "").strip()
        energy = (data.get("energy_feel") or "").strip() if kind == "share" else None
        if not allow:
            return False, reason or "Bu metin alana uygun görülmedi.", energy
        return True, "", energy or "sessiz bir yakınlık"
    except Exception:
        return True, "", "nötr bir titreşim" if kind == "share" else None
