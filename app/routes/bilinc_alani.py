import os
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.system_base import build_system_prompt

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

logger = logging.getLogger("sanri.bilinc")
logger.setLevel(logging.INFO)

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()

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

def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)

@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    user_text = req.text()
    session_id = (req.session_id or "default").strip()

    if not user_text:
        return AskResponse(response="", session_id=session_id)

    system_prompt = build_system_prompt(req.mode)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    client = get_client()

    try:
        response = client.responses.create(
            model=MODEL_NAME,
            input=messages,
            temperature=0.4,
            max_output_tokens=300,
        )

        reply = response.output_text.strip()

    except Exception as e:
        logger.exception("OpenAI call failed")
        raise HTTPException(status_code=500, detail=str(e))

    if not reply:
        reply = "Buradayım."

    return AskResponse(response=reply, session_id=session_id)