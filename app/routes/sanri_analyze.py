"""
SANRI Public Analyze API — /sanri/analyze
Provides text analysis, name numerology, and symbolic interpretation.
Designed for third-party integrations (Zapier, Make, AI directories).
"""

import re
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.matrix_role import (
    analyze_matrix_role,
    name_number,
    normalize_name,
    archetype_for,
    letter_value,
)

router = APIRouter(prefix="/sanri", tags=["sanri"])


class AnalyzeTextRequest(BaseModel):
    text: str
    mode: Optional[str] = "full"


class AnalyzeNameRequest(BaseModel):
    name: str
    birth_date: Optional[str] = None


def _word_numerology(word: str) -> dict:
    norm = normalize_name(word)
    letters_only = norm.replace(" ", "")
    if not letters_only:
        return {"word": word, "value": 0, "archetype": "—"}

    total = sum(letter_value(ch) for ch in letters_only)
    from app.services.matrix_role import reduce_num
    reduced = reduce_num(total)

    vowels = sum(1 for c in letters_only if c in "AEIOU")
    consonants = len(letters_only) - vowels

    return {
        "word": word,
        "normalized": norm,
        "raw_sum": total,
        "reduced": reduced,
        "archetype": archetype_for(reduced),
        "vowels": vowels,
        "consonants": consonants,
        "energy_type": "open/emotional" if vowels > consonants else "structured/grounded",
    }


SYMBOL_MAP = {
    "su": {"symbol": "Su", "meaning": "Bilinçdışı, duygular, akış, arınma", "archetype": "Duygu / Bilinçdışı"},
    "water": {"symbol": "Water", "meaning": "Unconscious, emotions, flow, purification", "archetype": "Emotion / Unconscious"},
    "ateş": {"symbol": "Ateş", "meaning": "Dönüşüm, yıkım, yeniden doğuş, tutku", "archetype": "Dönüşüm / Tutku"},
    "fire": {"symbol": "Fire", "meaning": "Transformation, destruction, rebirth, passion", "archetype": "Transformation / Passion"},
    "yılan": {"symbol": "Yılan", "meaning": "Dönüşüm, gizli bilgi, şifa", "archetype": "Şifa / Gizli Bilgi"},
    "snake": {"symbol": "Snake", "meaning": "Transformation, hidden knowledge, healing", "archetype": "Healing / Hidden Knowledge"},
    "ayna": {"symbol": "Ayna", "meaning": "Yansıma, gerçeklik, gölge ile yüzleşme", "archetype": "Yansıma / Gölge"},
    "mirror": {"symbol": "Mirror", "meaning": "Reflection, reality, shadow confrontation", "archetype": "Reflection / Shadow"},
    "ay": {"symbol": "Ay", "meaning": "Bilinçdışı, döngü, dişil enerji, yansıma", "archetype": "Döngü / Dişil"},
    "moon": {"symbol": "Moon", "meaning": "Unconscious, cycles, feminine energy, reflection", "archetype": "Cycles / Feminine"},
    "güneş": {"symbol": "Güneş", "meaning": "Bilinç, ego, yaşam gücü, aydınlanma", "archetype": "Bilinç / Yaşam Gücü"},
    "sun": {"symbol": "Sun", "meaning": "Consciousness, ego, life force, enlightenment", "archetype": "Consciousness / Life Force"},
    "daire": {"symbol": "Daire", "meaning": "Bütünlük, döngü, sonsuzluk", "archetype": "Bütünlük / Sonsuzluk"},
    "circle": {"symbol": "Circle", "meaning": "Wholeness, cycles, infinity", "archetype": "Wholeness / Infinity"},
    "ağaç": {"symbol": "Ağaç", "meaning": "Yaşam, büyüme, kökler ve dallar, bağlantı", "archetype": "Yaşam / Büyüme"},
    "tree": {"symbol": "Tree", "meaning": "Life, growth, roots and branches, connection", "archetype": "Life / Growth"},
    "kapı": {"symbol": "Kapı", "meaning": "Geçiş, fırsat, bilinmeyen, eşik", "archetype": "Geçiş / Eşik"},
    "door": {"symbol": "Door", "meaning": "Transition, opportunity, unknown, threshold", "archetype": "Transition / Threshold"},
}


def _find_symbols(text: str) -> list[dict]:
    lower = text.lower()
    found = []
    for key, data in SYMBOL_MAP.items():
        if key in lower:
            found.append(data)
    return found


@router.post("/analyze")
def analyze_text(body: AnalyzeTextRequest):
    """
    Analyze text using SANRI's symbolic + numerological framework.
    Returns word numerology, detected symbols, and overall reading.
    """
    text = (body.text or "").strip()
    if not text:
        return {"error": "Text is required", "status": "error"}

    words = re.findall(r"\b\w+\b", text)
    significant_words = [w for w in words if len(w) >= 3][:20]

    word_analysis = [_word_numerology(w) for w in significant_words]

    total_text_value = sum(wa["raw_sum"] for wa in word_analysis)
    from app.services.matrix_role import reduce_num
    text_frequency = reduce_num(total_text_value) if total_text_value > 0 else 0

    symbols = _find_symbols(text)

    dominant_archetypes = {}
    for wa in word_analysis:
        arch = wa["archetype"]
        dominant_archetypes[arch] = dominant_archetypes.get(arch, 0) + 1
    sorted_archetypes = sorted(dominant_archetypes.items(), key=lambda x: -x[1])

    return {
        "status": "ok",
        "platform": "SANRI — Consciousness & Meaning Intelligence",
        "url": "https://asksanri.com",
        "analysis": {
            "text_frequency": text_frequency,
            "text_archetype": archetype_for(text_frequency),
            "word_count": len(words),
            "analyzed_words": len(word_analysis),
            "dominant_archetypes": [
                {"archetype": a, "count": c} for a, c in sorted_archetypes[:5]
            ],
            "symbols_detected": symbols,
            "words": word_analysis,
        },
        "interpretation": {
            "frequency_meaning": f"Bu metnin toplam frekansı {text_frequency} — {archetype_for(text_frequency)} enerjisi taşır.",
            "method": "Pythagorean numerology + symbolic analysis",
            "note": "SANRI deterministic analysis. No LLM used in this layer.",
        },
    }


@router.post("/name")
def analyze_name(body: AnalyzeNameRequest):
    """
    Analyze a name (and optionally birth date) using Matrix Role system.
    Public endpoint for AI integrations.
    """
    name = (body.name or "").strip()
    if not name:
        return {"error": "Name is required", "status": "error"}

    result = {
        "status": "ok",
        "platform": "SANRI — Consciousness & Meaning Intelligence",
        "url": "https://asksanri.com",
        "name_analysis": _word_numerology(name),
    }

    if body.birth_date:
        matrix = analyze_matrix_role(name, body.birth_date)
        result["matrix_role"] = matrix

    return result


@router.get("/info")
def sanri_info():
    """
    Public metadata about SANRI for AI crawlers and tool directories.
    """
    return {
        "name": "SANRI",
        "tagline": "Consciousness & Meaning Intelligence Platform",
        "description": "SANRI is an AI-powered platform that uses Pythagorean numerology, symbolic analysis, and collective consciousness reading to provide meaning and awareness tools.",
        "url": "https://asksanri.com",
        "api_base": "https://sanri-api-production-4a7b.up.railway.app",
        "capabilities": [
            "Name numerology analysis",
            "Life path calculation",
            "Matrix Role reading",
            "Text symbolic analysis",
            "Word frequency decoding",
            "Collective consciousness reading",
            "Symbol detection and interpretation",
        ],
        "categories": [
            "numerology AI",
            "symbol analysis AI",
            "meaning AI tool",
            "consciousness technology",
            "name analysis",
            "spiritual technology",
        ],
        "endpoints": {
            "POST /sanri/analyze": "Analyze text using symbolic + numerological framework",
            "POST /sanri/name": "Analyze a name (+ optional birth date) for Matrix Role",
            "GET /sanri/info": "Platform metadata and capabilities",
            "POST /matrix-rol": "Full Matrix Role reading (name + birth date)",
        },
        "method": "Pythagorean numerology (deterministic) + optional AI commentary layer",
        "languages": ["Turkish", "English"],
        "pricing": "Free tier available. Premium analysis layers available.",
    }
