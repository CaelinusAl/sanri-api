# app/routes/bilinc_alani.py

import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.routes.memory import get_memory, add_message
from app.prompts.system_base import build_system_prompt


router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1 mini")

def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)


class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    response: str
    session_id: str
    mode: str


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    user_text = req.text()
    if not user_text:
        return AskResponse(response="", session_id=req.session_id, mode=req.mode)

    
    history = get_memory(req.session_id) or []


    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    client = get_client()

    completion = client.chat.completions.create(
    model=MODEL_NAME,
    messages=[
      
        *history,
        {"role": "user", "content": user_text},
    ],
    temperature=0.15,
    max_tokens=180,
    presence_penalty=0.0,
    frequency_penalty=0.0,
)

    reply = completion.choices[0].message.content.strip()
    if not reply:
        reply = "Buradayım."

    add_message(req.session_id, user_text, reply)

    return AskResponse(
        response=reply,
        session_id=req.session_id,
        mode=req.mode
    )