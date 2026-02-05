import os
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from openai import OpenAI

from app.prompts.system_base import build_system_prompt

logger = logging.getLogger("sanri.bilinc_alani")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
EXPECTED_SANRI_TOKEN = (os.getenv("SANRI_TOKEN") or "").strip()


class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    domain: Optional[str] = ""
    mode: Optional[str] = "user"


class AskResponse(BaseModel):
    response: str
    session_id: Optional[str] = None


def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


def check_token(x_sanri_token: Optional[str]) -> None:
    # Token kontrolü opsiyonel: SANRI_TOKEN tanımlıysa kontrol eder, yoksa kapalıdır.
    if not EXPECTED_SANRI_TOKEN:
        return
    if (x_sanri_token or "").strip() != EXPECTED_SANRI_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid x-sanri-token")


def extract_user_text(req: AskRequest) -> str:
    return (req.message or req.question or "").strip()


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
        completion = client.responses.create(
            model=MODEL_NAME,
            input=messages,
            temperature=0.4,
            max_output_tokens=300,
        )

        reply = completion.output_text

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not reply:
        reply = "Buradayım."

    return AskResponse(response=reply, session_id=session_id)