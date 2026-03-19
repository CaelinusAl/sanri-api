from typing import List, Optional

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
                SELECT content
                FROM user_memory
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"uid": int(x_user_id)},
        ).mappings().all()

        memory_text = "\n".join(
            [str(row["content"]).strip() for row in memory_rows if row.get("content")]
        ).strip()

        if not memory_text:
            memory_text = "No prior memory."

        system_prompt = (
            build_system_prompt("user")
            + "\n\n"
            + "MEMORY:\n"
            + memory_text
            + "\n\n"
            + "CRITICAL RULES:\n"
            + "1. If the user asks whether you remember, you MUST use MEMORY.\n"
            + "2. If there is relevant past context, mention it directly.\n"
            + "3. Do not become abstract when memory is available.\n"
            + "4. Stay short, clear, deep, and human.\n"
        )

        user_input = f"""
IMPORTANT:

User previously said:
{memory_text}

Now user asks:
{user_message}

RULE:
If user is asking about past, you MUST answer directly using memory.

Do NOT reflect.
Do NOT go abstract.
Answer clearly.

Example:
User: "Az önce ne yazdım?"
You: "Az önce '...' yazdın."

Now respond:
"""

        print("SANRI MODEL =", MODEL)
        print("SANRI USER ID =", x_user_id)
        print("SANRI USER MESSAGE =", user_message)
        print("SANRI MEMORY =", memory_text[:300])

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

        print("SANRI RESPONSE =", text_resp[:300])

        # ============================
        # MEMORY SAVE
        # ============================
        try:
            db.execute(
                text("""
                    INSERT INTO user_memory (user_id, type, content)
                    VALUES (:uid, :type, :content)
                """),
                {
                    "uid": int(x_user_id),
                    "type": "chat",
                    "content": user_message + " -> " + text_resp,
                },
            )
            db.commit()
        except Exception as e:
            print("MEMORY SAVE ERROR =", str(e))

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
            "prompt_version": "fallback_v6",
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
            SELECT content, created_at
            FROM user_memory
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"uid": int(x_user_id)},
    ).mappings().all()

    return rows