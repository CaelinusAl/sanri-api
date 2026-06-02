import json
import os

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.prompts.system_base import build_system_prompt, SANRI_PROMPT_VERSION
from app.services.ai_service import get_client, generate_sanri_response
from app.services.memory_service import load_memory, save_memory
from app.services.profile_service import (
    load_profile,
    build_runtime_profile,
    build_profile_prompt,
    save_profile,
)

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


def normalize_ending(text_resp: str) -> str:
    """Yanıtı yalnızca yumuşakça temizler.

    Artık soruları SİLMEZ — Sanrı gerektiğinde içten bir soruyla bitirebilir.
    Sadece cümlenin uygun bir noktalama ile bittiğinden emin olur.
    """
    text_resp = (text_resp or "").strip()
    if not text_resp:
        return text_resp

    if text_resp[-1] not in ".!?…":
        text_resp += "."

    return text_resp


def get_daily_message_count(db: Session, user_id: int) -> int:
    try:
        row = db.execute(
            text("""
                SELECT COUNT(*) AS count
                FROM user_memory
                WHERE user_id = :uid
                  AND type = 'user'
                  AND DATE(created_at) = CURRENT_DATE
            """),
            {"uid": user_id},
        ).mappings().first()

        return int(row["count"]) if row and row.get("count") is not None else 0
    except Exception as e:
        print("SANRI DAILY COUNT ERROR =", repr(e))
        return 0


def check_is_premium(db: Session, user_id: int) -> bool:
    try:
        row = db.execute(
            text("""
                SELECT is_premium
                FROM users
                WHERE id = :uid
                LIMIT 1
            """),
            {"uid": user_id},
        ).mappings().first()

        if not row:
            return False

        return bool(row.get("is_premium"))
    except Exception as e:
        print("SANRI PREMIUM CHECK ERROR =", repr(e))
        return False


def run_sanri(
    db: Session,
    user_id: int,
    user_message: str,
    session_id: str,
    lang: str = "tr",
    system_context: str = None,
    gate_name: str = None,
) -> dict:
    is_premium = check_is_premium(db, user_id)
    daily_count = get_daily_message_count(db, user_id)

    if not is_premium and daily_count >= 10:
        limit_text = (
            "Bugünlük ücretsiz kullanım sınırına ulaştın. "
            "Yarın tekrar deneyebilir veya premium erişime geçebilirsin."
        )

        return {
            "answer": limit_text,
            "response": limit_text,
            "session_id": session_id,
            "prompt_version": "limit_v1",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    memory_text = load_memory(db, user_id)
    existing_profile = load_profile(db, user_id)
    runtime_profile = build_runtime_profile(existing_profile, user_message)

    profile_text = json.dumps(runtime_profile, ensure_ascii=False)
    profile_prompt = build_profile_prompt(runtime_profile)

    lang_instruction = (
        "Respond in Turkish."
        if (lang or "tr").lower() == "tr"
        else "Respond in English."
    )

    gate_block = ""
    if system_context:
        gate_label = gate_name or "Gate"
        gate_block = (
            f"\n\nACTIVE GATE: {gate_label}\n"
            f"GATE INSTRUCTIONS (follow these strictly, they define your tone and behavior for this gate):\n"
            f"{system_context}\n"
        )

    system_prompt = (
        build_system_prompt("user")
        + "\n\n"
        + lang_instruction
        + gate_block
        + "\n\n"
        + profile_prompt
        + "\n\n"
        + "MEMORY:\n"
        + memory_text
        + "\n\n"
        + "USER PROFILE:\n"
        + profile_text
        + "\n\n"
        + "CRITICAL RULES:\n"
        + "1. If the user asks what they said before, who said what, or whether you remember, answer directly and concretely from MEMORY — do not go abstract.\n"
        + "2. FEEL the user first: sense and gently name the emotion beneath their words.\n"
        + "3. Hold up a CLEAR mirror — make the pattern, need, or contradiction visible. Deep but never vague.\n"
        + "4. Keep it short and human: 3-6 sentences, warm natural prose. No lists, no markdown, no section tags.\n"
        + "5. Ask AT MOST ONE caring, specific question, and only when it genuinely helps you understand the person. Place it at the very end to invite them to keep talking. Often no question is needed.\n"
        + "6. Never interrogate, never stack questions, never use hollow filler questions.\n"
        + "7. When it fits, close with one small, concrete next step, anchor, or reframe — do not leave the person in the void.\n"
        + "8. End EITHER with a gentle question (rule 5) OR with a small step/insight (rule 7) — whichever truly serves this person now.\n"
        + "9. No mystical jargon, no hollow affirmations, no moralizing, no commanding 'yapmalısın'.\n"
        + "10. If the user says they do not want questions, ask zero questions and give a direct, warm reflection plus one small step.\n"
        + "11. Gate / awakened context: hold the gate's tone and imagery, but stay warm, clear, and human.\n"
    )

    user_input = f"""
IMPORTANT:

User profile:
{profile_text}

Conversation memory:
{memory_text}

Current user message:
{user_message}

RULE:
If the user is asking about past conversation, memory, or recall, answer directly using memory.
Do NOT go abstract in those cases.

HOW TO RESPOND:
Önce kullanıcıyı hisset ve duygusunu nazikçe adlandır.
Net bir ayna tut — örüntüyü görünür kıl, ama bulanık olma.
Anlamak için gerçekten gerekiyorsa, SONDA tek bir içten soru sorabilirsin (her seferinde değil).
Gerekmiyorsa, taşıyabileceği küçük bir adım ya da içgörüyle bitir.
Kullanıcı soru istemiyorsa hiç soru sorma; yine de sıcak bir yansıma ve küçük bir yön ver.
3-6 cümle, sıcak ve insani konuş.

Now respond:
""".strip()

    try:
        client = get_client()

        text_resp = generate_sanri_response(
            client=client,
            model=MODEL,
            system_prompt=system_prompt,
            user_input=user_input,
        )

        text_resp = normalize_ending(text_resp)

    except Exception as e:
        print("SANRI OPENAI ERROR =", repr(e))

        fallback_text = "Sanrı seni duyuyor. Şu an cevap akışı kısa bir sessizlikten geçiyor."

        return {
            "answer": fallback_text,
            "response": fallback_text,
            "session_id": session_id,
            "prompt_version": "fallback_v11",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    save_memory(db, user_id, user_message, text_resp)
    save_profile(db, user_id, runtime_profile)

    return {
        "answer": text_resp,
        "response": text_resp,
        "session_id": session_id,
        "prompt_version": SANRI_PROMPT_VERSION,
        "title": None,
        "message": None,
        "steps": None,
        "closing": None,
    }