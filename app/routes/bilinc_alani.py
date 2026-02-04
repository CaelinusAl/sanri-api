# app/routes/bilinc_alani.py
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.routes.memory import get_memory, add_message
from app.prompts.system_base import build_system_prompt

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)

class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    domain: Optional[str] = None
    mode: Optional[str] = "user"

    def text(self) -> str:
        return (self.message or self.question or "").strip()

class AskResponse(BaseModel):
    response: str
    session_id: str

@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    user_text = req.text()
    session_id = (req.session_id or "default").strip()

    if not user_text:
        return AskResponse(response="", session_id=session_id)

    system_prompt = build_system_prompt(req.mode)

    history = get_memory(session_id) or []

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    client = get_client()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.4,
            max_tokens=300,
        )

        reply = completion.choices[0].message.content or ""

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    reply = reply.strip() if reply else "Buradayım."

    add_message(session_id, user_text, reply)
    return AskResponse(response=reply, session_id=session_id)