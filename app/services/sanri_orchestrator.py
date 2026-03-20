import json
import os

from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from app.prompts.system_base import build_system_prompt, SANRI_PROMPT_VERSION
from app.services.ai_service import generate_sanri_response
from app.services.memory_service import load_memory, save_memory
from app.services.profile_service import (
    load_profile,
    build_runtime_profile,
    build_profile_prompt,
    save_profile,
)

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


def get_client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    print("DEBUG OPENAI KEY =", key[:10] if key else "NONE")
    print("DEBUG OPENAI MODEL =", MODEL)

    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)


def run_sanri(
    db: Session,
    user_id: int,
    user_message: str,
    session_id: str,
    lang: str = "tr",
) -> dict:
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

    system_prompt = (
        build_system_prompt("user")
        + "\n\n"
        + lang_instruction
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
        + "4. Stay short, human, conscious, and clear.\n"
        + "5. Maximum 4 sentences.\n"
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

Now respond:
""".strip()

    print("SANRI USER ID =", user_id)
    print("SANRI USER MESSAGE =", user_message)
    print("SANRI MEMORY =", memory_text[:500])
    print("SANRI PROFILE =", profile_text[:500])

    try:
        client = get_client()
        text_resp = generate_sanri_response(
            client=client,
            model=MODEL,
            system_prompt=system_prompt,
            user_input=user_input,
        )
        print("SANRI RESPONSE =", text_resp[:500])

    except Exception as e:
        print("SANRI OPENAI ERROR =", repr(e))
        text_resp = "Sanrı şu an sessizlikte cevap veriyor."

        return {
            "answer": text_resp,
            "response": text_resp,
            "session_id": session_id,
            "prompt_version": "fallback_v10",
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