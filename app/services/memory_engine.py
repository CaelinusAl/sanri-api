from __future__ import annotations

from collections import Counter
from typing import Any


KEYWORD_MAP = {
    "love": ["love", "aşk", "sevgi", "kalp", "heart"],
    "fear": ["fear", "korku", "endişe", "anxiety", "panic"],
    "dream": ["dream", "rüya", "uyku", "sezgi", "vision"],
    "money": ["money", "para", "bolluk", "abundance", "wealth"],
    "purpose": ["purpose", "amaç", "yol", "mission", "calling"],
    "identity": ["identity", "kimlik", "ben kimim", "self", "ego"],
    "relationship": ["relationship", "ilişki", "partner", "sevgili", "evlilik"],
    "body": ["body", "beden", "rahim", "womb", "energy", "kundalini"],
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def extract_patterns(history: list[dict[str, Any]]) -> list[str]:
    hits: list[str] = []

    for item in history:
        text = _normalize(
            f"{item.get('message', '')} {item.get('response', '')}"
        )

        for tag, variants in KEYWORD_MAP.items():
            if any(v in text for v in variants):
                hits.append(tag)

    counts = Counter(hits)
    return [tag for tag, _ in counts.most_common(5)]


def build_memory_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = extract_patterns(history)

    dominant = patterns[0] if patterns else ""
    secondary = patterns[1:3] if len(patterns) > 1 else []

    return {
        "dominant_pattern": dominant,
        "secondary_patterns": secondary,
        "all_patterns": patterns,
        "memory_line": _build_memory_line(dominant, secondary),
    }


def _build_memory_line(dominant: str, secondary: list[str]) -> str:
    if not dominant:
        return "No strong recurring pattern detected yet."

    if secondary:
        return (
            f"Recurring theme: {dominant}. "
            f"Secondary signals: {', '.join(secondary)}."
        )

    return f"Recurring theme: {dominant}."