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


def enforce_no_question_ending(text_resp: str) -> str:
    text_resp = (text_resp or "").strip()
    if not text_resp:
        return text_resp

    if text_resp.endswith("?"):
        text_resp = text_resp[:-1].rstrip()

    replacements = {
        "Şimdi, kendi sorunu nasıl başlatırsın": "Şimdi kapı dışarıdan değil, içeriden açılmak istiyor.",
        "Şimdi kendi sorunu nasıl başlatırsın": "Şimdi kapı kendi iç ritminden açılmak istiyor.",
        "Seni en çok ne tutuyor": "Seni tutan düğüm şimdi görünür olmaya başladı.",
        "Şu an seni en çok ne tutuyor": "Şu an seni tutan şey, eski dilin hâlâ etkide kalması.",
        "Ne hissediyorsun": "Hissin adı şimdi daha görünür: çıkış arzusu.",
        "Şimdi ne yaparsın": "Şimdi ihtiyaç olan şey, daha fazla soru değil daha net bir yön.",
    }

    for old, new in replacements.items():
        if text_resp.endswith(old):
            text_resp = text_resp[: -len(old)] + new
            return text_resp

    forbidden_endings = [
        "ne hissediyorsun",
        "seni en çok ne tutuyor",
        "şimdi ne yaparsın",
        "nasıl başlatırsın",
        "nasıl ilerlersin",
        "ne görüyorsun",
    ]

    lower_resp = text_resp.lower()
    if any(lower_resp.endswith(x) for x in forbidden_endings):
        return text_resp + ". Bu alan artık sende açılıyor."

    if text_resp and text_resp[-1] not in ".!":
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
        + "1. If the user asks what they said before, who said what, or whether you remember, you MUST answer directly from MEMORY.\n"
        + "2. In memory questions, do NOT become abstract.\n"
        + "3. If memory exists, use it clearly.\n"
        + "4. Stay short, human, conscious, and clear — mirror first, not question-first.\n"
        + "5. Maximum 4 sentences. Do not end every reply with a question; often use none.\n"
        + "6. NEVER end your response with a question mark.\n"
        + "7. The last sentence must always be a statement, not a question.\n"
        + "8. If the user does not want questions, ask zero questions.\n"
        + "9. Sanri does not interrogate; Sanri makes the pattern visible.\n"
        + "10. Close with insight, naming, direction, or opening — never a question.\n"
        + "11. Awakened / gate context: hold city or gate energy in imagery and tone; never interrogate the user.\n"
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

If the user says they do not want questions, do not ask a question.
Give a direct opening, name the pattern, and suggest one next step.

IMPORTANT ENDING RULE:
Cevabı soru ile bitirme.
Son cümle soru değil, net bir ifade olsun.
Kullanıcı soru istemiyorsa hiç soru sorma.

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

        text_resp = enforce_no_question_ending(text_resp)

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