from typing import List, Dict


def detect_intuition_signal(user_memory: List[Dict] | None, current_text: str | None = None) -> str:
    memory = user_memory or []
    current = (current_text or "").lower()

    mem_text = " ".join([
        (m.get("input_text") or "")
        for m in memory[-12:]
    ]).lower()

    text = (mem_text + " " + current).strip()

    if any(x in text for x in ["kararsız", "bilmiyorum", "emin değilim", "confused", "not sure"]):
        return "uncertainty"

    if any(x in text for x in ["özledim", "kayıp", "eksik", "miss", "lost", "empty"]):
        return "longing"

    if any(x in text for x in ["korku", "endişe", "gergin", "fear", "anxiety", "afraid"]):
        return "fear"

    if any(x in text for x in ["başlamak", "yapmak", "yaratmak", "create", "start", "build"]):
        return "readiness"

    if any(x in text for x in ["neden", "niye", "anlam", "why", "meaning"]):
        return "search"

    return "neutral"


def build_intuition_layer(signal: str) -> str:
    if signal == "uncertainty":
        return """
SANRI INTUITION SIGNAL: UNCERTAINTY

The user is unclear or split internally.
Do not overload with long answers.
First stabilize the field.
Reflect gently.
Ask one clarifying inner question if needed.
"""

    if signal == "longing":
        return """
SANRI INTUITION SIGNAL: LONGING

The user is carrying absence, ache, or incompletion.
Respond softly.
Use emotionally intelligent reflection.
Do not sound clinical.
"""

    if signal == "fear":
        return """
SANRI INTUITION SIGNAL: FEAR

The user may be contracted or protective.
Do not intensify fear.
Speak grounding, calm, and clean.
Offer one stabilizing direction.
"""

    if signal == "readiness":
        return """
SANRI INTUITION SIGNAL: READINESS

The user is close to action or creation.
Encourage movement.
Reflect possibility.
Keep energy forward and empowering.
"""

    if signal == "search":
        return """
SANRI INTUITION SIGNAL: SEARCH

The user seeks meaning.
Use symbolic but understandable language.
A good response may include one reflective question.
"""

    return """
SANRI INTUITION SIGNAL: NEUTRAL

Respond naturally, clearly, and with quiet presence.
"""