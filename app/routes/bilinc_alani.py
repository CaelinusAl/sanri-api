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


# ================================
# SCHEMA
# ================================
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


# ================================
# OPENAI CLIENT
# ================================
def get_client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()

    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)


# ================================
# ANALYSIS
# ================================
def analyze_user_signal(text_value: str) -> dict:
    t = (text_value or "").lower()

    dominant_emotion = "neutral"
    intent = "reflection"
    pattern = "general"

    if any(k in t for k in ["geçmiş", "hatırla", "önce"]):
        intent = "memory"
        pattern = "past_reference"

    if any(k in t for k in ["korku", "endişe"]):
        dominant_emotion = "fear"

    if any(k in t for k in ["yalnız", "boşluk"]):
        dominant_emotion = "loneliness"

    if any(k in t for k in ["nasıl", "ne yapmalıyım"]):
        intent = "direction"
        pattern = "guidance_need"

    if any(k in t for k in ["aşk", "sevgi"]):
        dominant_emotion = "love"

    return {
        "dominant_emotion": dominant_emotion,
        "intent": intent,
        "pattern": pattern,
    }


def detect_level(data: dict) -> dict:
    emotion = data.get("dominant_emotion")
    intent = data.get("intent")

    level = 1
    archetype = "mirror"
    tone = "clear"

    if intent == "memory":
        level = 2
        archetype = "rememberer"

    if emotion in ["love", "loneliness"]:
        level = 3
        archetype = "heart_reader"

    if intent == "direction":
        level = 4
        archetype = "path_opener"

    return {
        "sanri_level": level,
        "sanri_archetype": archetype,
        "sanri_tone": tone,
    }


# ================================
# ASK
# ================================
@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_user_id: str = Header(None), db: Session = Depends(get_db)):

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
        try:
            rows = db.execute(
                text("""
                    SELECT type, content
                    FROM user_memory
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT 6
                """),
                {"uid": int(x_user_id)},
            ).mappings().all()

            memory_text = "\n".join(
                [f"{r['type']}: {r['content']}" for r in rows]
            )

        except:
            memory_text = ""

        # ============================
        # PROFILE
        # ============================
        analyzed = analyze_user_signal(user_message)
        level_data = detect_level(analyzed)

        profile = {**analyzed, **level_data}

        system_prompt = (
            build_system_prompt("user")
            + "\n\nPROFILE:\n"
            + json.dumps(profile, ensure_ascii=False)
            + "\n\nMEMORY:\n"
            + memory_text
        )

        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=1.0,
            max_tokens=400,
        )

        text_resp = (completion.choices[0].message.content or "").strip()

        if not text_resp:
            text_resp = "Sanrı seni duydu."

        # ============================
        # MEMORY SAVE
        # ============================
        try:
            db.execute(
                text("""
                    INSERT INTO user_memory (user_id, type, content)
                    VALUES (:uid, 'user', :content)
                """),
                {"uid": int(x_user_id), "content": user_message},
            )

            db.execute(
                text("""
                    INSERT INTO user_memory (user_id, type, content)
                    VALUES (:uid, 'ai', :content)
                """),
                {"uid": int(x_user_id), "content": text_resp},
            )

            db.commit()
        except Exception as e:
            print("MEMORY SAVE ERROR:", e)

        return {
            "answer": text_resp,
            "response": text_resp,
            "session_id": req.session_id,
            "prompt_version": SANRI_PROMPT_VERSION,
        }

    except Exception as e:
        print("SANRI ERROR:", e)

        return {
            "answer": "Sanrı şu an sessizlikte cevap veriyor.",
            "response": "Sanrı şu an sessizlikte cevap veriyor.",
            "session_id": req.session_id,
            "prompt_version": "fallback_final",
        }


# ================================
# MEMORY GET
# ================================
@router.get("/memory")
def get_memory(x_user_id: str = Header(None), db: Session = Depends(get_db)):

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


# ================================
# PROFILE GET
# ================================
@router.get("/profile")
def get_profile(x_user_id: str = Header(None), db: Session = Depends(get_db)):

    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    return {
        "user_id": int(x_user_id),
        "status": "active",
    }