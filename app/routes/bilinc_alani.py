# app/routes/bilinc_alani.py
import os
import traceback
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.system_base import build_system_prompt

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

# Model
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

# =======================
# Schemas
# =======================

class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"  # user | test | cocuk

    def text(self) -> str:
        return (self.message or self.question or "").strip()

class AskResponse(BaseModel):
    response: str
    session_id: str

# =======================
# OpenAI Client
# =======================

def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY missing or empty"
        )
    return OpenAI(api_key=api_key)

# =======================
# Main Endpoint
# =======================

@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_sanri_token: Optional[str] = Header(default=None)
):
    user_text = req.text()
    session_id = (req.session_id or "default").strip()

    if not user_text:
        return AskResponse(response="", session_id=session_id)

    system_prompt = build_system_prompt(req.mode)

    try:
        client = get_client()

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=float(os.getenv("SANRI_TEMPERATURE", "0.4")),
            max_tokens=int(os.getenv("SANRI_MAX_TOKENS", "300")),
        )

        reply = (completion.choices[0].message.content or "").strip()

    except Exception as e:
        # 🔥 GERÇEK HATAYI LOG’A BAS
        print("🔥 SANRI LLM ERROR 🔥")
        print(repr(e))
        print(traceback.format_exc())
        print("SANRI PROMPT LOADED:", system_prompt[:120])

        raise HTTPException(
            status_code=500,
            detail=f"LLM_ERROR: {str(e)}"
        )

    if not reply:
        reply = "Buradayım."

    return AskResponse(response=reply, session_id=session_id)