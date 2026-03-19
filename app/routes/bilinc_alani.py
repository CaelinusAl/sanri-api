from typing import List, Optional
import json
import os

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.prompts.system_base import build_system_prompt, SANRI_PROMPT_VERSION

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


class AskRequest(BaseModel):
    message: str
    session_id: str = "default"
    lang: str = "tr"


class AskResponse(BaseModel):
    answer: str
    response: str
    session_id: str
    prompt_version: str
    title: Optional[str] = None
    message: Optional[str] = None
    steps: Optional[List[str]] = None
    closing: Optional[str] = None


def get_client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    print("DEBUG OPENAI KEY =", key[:10] if key else "NONE")

    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)


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


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    user_message = (req.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")

    try:
        client = get_client()

        # ============================
        # MEMORY GET
        # ============================
        memory_rows = db.execute(
            text("""
                SELECT type, content
                FROM user_memory
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT 8
            """),
            {"uid": int(x_user_id)},
        ).mappings().all()

        memory_text = "\n".join(
            [
                f"{row['type']}: {str(row['content']).strip()}"
                for row in memory_rows
                if row.get("content")
            ]
        ).strip()

        if not memory_text:
            memory_text = "No prior memory."

        # ============================
        # PROFILE GET
        # ============================
        profile_row = db.execute(
            text("""
                SELECT data
                FROM user_profiles
                WHERE user_id = :uid
                LIMIT 1
            """),
            {"uid": int(x_user_id)},
        ).mappings().first()

        profile_data = {}
        if profile_row and profile_row.get("data"):
            try:
                raw_data = profile_row["data"]
                if isinstance(raw_data, dict):
                    profile_data = raw_data
                else:
                    profile_data = json.loads(raw_data)
            except Exception:
                profile_data = {}

        # ============================
        # RUNTIME PROFILE
        # ============================
        runtime_analyzed = analyze_user_signal(user_message)
        runtime_level_data = detect_sanri_level({**profile_data, **runtime_analyzed})
        runtime_profile = {
            **profile_data,
            **runtime_analyzed,
            **runtime_level_data,
        }

        profile_text = json.dumps(runtime_profile, ensure_ascii=False)
        profile_prompt = build_profile_prompt(runtime_profile)

        system_prompt = (
            build_system_prompt("user")
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

        print("SANRI MODEL =", MODEL)
        print("SANRI USER ID =", x_user_id)
        print("SANRI USER MESSAGE =", user_message)
        print("SANRI MEMORY =", memory_text[:500])
        print("SANRI PROFILE =", profile_text[:500])

        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_input,
                },
            ],
            temperature=1.0,
            max_tokens=500,
        )

        text_resp = (completion.choices[0].message.content or "").strip()

        if not text_resp:
            text_resp = "Sanrı seni duydu."

        print("SANRI RESPONSE =", text_resp[:500])

        try:
            # user memory
            db.execute(
                text("""
                    INSERT INTO user_memory (user_id, type, content)
                    VALUES (:uid, :type, :content)
                """),
                {
                    "uid": int(x_user_id),
                    "type": "user",
                    "content": user_message,
                },
            )

            # ai memory
            db.execute(
                text("""
                    INSERT INTO user_memory (user_id, type, content)
                    VALUES (:uid, :type, :content)
                """),
                {
                    "uid": int(x_user_id),
                    "type": "ai",
                    "content": text_resp,
                },
            )

            # profile upsert
            existing_profile = db.execute(
                text("""
                    SELECT id
                    FROM user_profiles
                    WHERE user_id = :uid
                    LIMIT 1
                """),
                {"uid": int(x_user_id)},
            ).mappings().first()

            if existing_profile:
                db.execute(
                    text("""
                        UPDATE user_profiles
                        SET data = :data,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :uid
                    """),
                    {
                        "uid": int(x_user_id),
                        "data": json.dumps(runtime_profile, ensure_ascii=False),
                    },
                )
            else:
                db.execute(
                    text("""
                        INSERT INTO user_profiles (user_id, data, updated_at)
                        VALUES (:uid, :data, CURRENT_TIMESTAMP)
                    """),
                    {
                        "uid": int(x_user_id),
                        "data": json.dumps(runtime_profile, ensure_ascii=False),
                    },
                )

            db.commit()

        except Exception as e:
            print("MEMORY / PROFILE SAVE ERROR =", str(e))

        return {
            "answer": text_resp,
            "response": text_resp,
            "session_id": req.session_id,
            "prompt_version": SANRI_PROMPT_VERSION,
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    except Exception as e:
        print("SANRI OPENAI ERROR =", repr(e))

        fallback = "Sanrı şu an sessizlikte cevap veriyor."

        return {
            "answer": fallback,
            "response": fallback,
            "session_id": req.session_id,
            "prompt_version": "fallback_v8",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }


@router.get("/memory")
def get_memory(
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    rows = db.execute(
        text("""
            SELECT type, content, created_at
            FROM user_memory
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"uid": int(x_user_id)},
    ).mappings().all()

    return rows


@router.get("/profile")
def get_profile(
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    row = db.execute(
        text("""
            SELECT user_id, data, updated_at
            FROM user_profiles
            WHERE user_id = :uid
            LIMIT 1
        """),
        {"uid": int(x_user_id)},
    ).mappings().first()

    if not row:
        return {
            "user_id": int(x_user_id),
            "data": {},
            "updated_at": None,
        }

    parsed = {}
    try:
        raw_data = row["data"]
        if isinstance(raw_data, dict):
            parsed = raw_data
        else:
            parsed = json.loads(raw_data)
    except Exception:
        parsed = {}

    return {
        "user_id": row["user_id"],
        "data": parsed,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }