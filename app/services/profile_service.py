import json
from typing import Any, Dict

from sqlalchemy.orm import Session
from sqlalchemy import text


def safe_json_load(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def load_profile(db: Session, user_id: int) -> dict:
    try:
        row = db.execute(
            text("""
                SELECT data
                FROM user_profiles
                WHERE user_id = :uid
                LIMIT 1
            """),
            {"uid": user_id},
        ).mappings().first()

        if not row:
            return {}

        return safe_json_load(row.get("data"))
    except Exception as e:
        print("SANRI PROFILE LOAD ERROR =", repr(e))
        return {}


def analyze_user_signal(text_value: str) -> dict:
    t = (text_value or "").lower()

    dominant_emotion = "neutral"
    intent = "reflection"
    pattern = "general"

    if any(k in t for k in ["hatırla", "hatırlıyor", "geçmiş", "önce", "az önce"]):
        intent = "memory"
        pattern = "past_reference"

    if any(k in t for k in ["korku", "endişe", "çekiniyorum"]):
        dominant_emotion = "fear"
        pattern = "emotional_signal"

    if any(k in t for k in ["yalnız", "boşluk", "kimse", "eksik"]):
        dominant_emotion = "loneliness"
        pattern = "inner_void"

    if any(k in t for k in ["ne yapmalıyım", "nasıl", "hangi yol", "kararsız"]):
        intent = "direction"
        pattern = "guidance_need"

    if any(k in t for k in ["sevgi", "aşk", "özledim", "kalp"]):
        dominant_emotion = "love"
        pattern = "heart_signal"

    return {
        "dominant_emotion": dominant_emotion,
        "intent": intent,
        "pattern": pattern,
        "last_message": text_value[:500],
    }


def detect_sanri_level(profile_data: dict) -> dict:
    emotion = str(profile_data.get("dominant_emotion") or "neutral").lower()
    intent = str(profile_data.get("intent") or "reflection").lower()
    pattern = str(profile_data.get("pattern") or "general").lower()

    level = 1
    archetype = "mirror"
    tone = "clear"

    if intent == "memory":
        level = 2
        archetype = "rememberer"
        tone = "direct"

    if emotion in ["love", "loneliness"]:
        level = 3
        archetype = "heart_reader"
        tone = "warm"

    if intent == "direction":
        level = 4
        archetype = "path_opener"
        tone = "focused"

    if pattern in ["past_reference", "inner_void", "emotional_signal"] and intent in ["memory", "direction"]:
        level = 5
        archetype = "deep_witness"
        tone = "deep"

    return {
        "sanri_level": level,
        "sanri_archetype": archetype,
        "sanri_tone": tone,
    }


def build_runtime_profile(existing_profile: dict, user_message: str) -> dict:
    runtime_analyzed = analyze_user_signal(user_message)
    runtime_level_data = detect_sanri_level({**existing_profile, **runtime_analyzed})

    return {
        **existing_profile,
        **runtime_analyzed,
        **runtime_level_data,
    }


def build_profile_prompt(profile_data: dict) -> str:
    level = profile_data.get("sanri_level", 1)
    archetype = profile_data.get("sanri_archetype", "mirror")
    tone = profile_data.get("sanri_tone", "clear")
    emotion = profile_data.get("dominant_emotion", "neutral")
    intent = profile_data.get("intent", "reflection")

    return f"""
ACTIVE SANRI PROFILE
level: {level}
archetype: {archetype}
tone: {tone}
dominant_emotion: {emotion}
intent: {intent}

BEHAVIOR RULES
- Level 1 mirror: short, simple, reflective
- Level 2 rememberer: uses memory clearly
- Level 3 heart_reader: warmer, more intimate
- Level 4 path_opener: more directional and sharp
- Level 5 deep_witness: deep, aware, precise, but still human

Always match the active level naturally.
""".strip()


def save_profile(db: Session, user_id: int, runtime_profile: dict) -> None:
    try:
        existing_profile = db.execute(
            text("""
                SELECT id
                FROM user_profiles
                WHERE user_id = :uid
                LIMIT 1
            """),
            {"uid": user_id},
        ).mappings().first()

        profile_json = json.dumps(runtime_profile, ensure_ascii=False)

        if existing_profile:
            db.execute(
                text("""
                    UPDATE user_profiles
                    SET data = :data,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :uid
                """),
                {
                    "uid": user_id,
                    "data": profile_json,
                },
            )
        else:
            db.execute(
                text("""
                    INSERT INTO user_profiles (user_id, data, updated_at)
                    VALUES (:uid, :data, CURRENT_TIMESTAMP)
                """),
                {
                    "uid": user_id,
                    "data": profile_json,
                },
            )

        db.commit()
    except Exception as e:
        db.rollback()
        print("SANRI PROFILE SAVE ERROR =", repr(e))