# app/routes/bilinc_alani.py
import os
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from openai import OpenAI

# Senin projende varsa:
from app.prompts.system_base import build_system_prompt  # build_system_prompt(mode) -> str

logger = logging.getLogger("sanri.bilinc_alani")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

# Varsayılan model (Railway'de OPENAI_MODEL ile override edebilirsin)
MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

# İstersen panel token kontrolü için Railway'ye SANRI_TOKEN koy
EXPECTED_SANRI_TOKEN = (os.getenv("SANRI_TOKEN") or "").strip()


class AskRequest(BaseModel):
    # Panel bazen message gönderiyor, bazen question. İkisini de kabul ediyoruz.
    message: Optional[str] = None
    question: Optional[str] = None

    session_id: Optional[str] = "default"
    domain: Optional[str] = ""
    mode: Optional[str] = "user"


class AskResponse(BaseModel):
    response: str
    session_id: Optional[str] = None


def get_client() -> OpenAI:
    """
    OpenAI client oluşturur.
    OPENAI_API_KEY (veya geriye dönük OPENAI_KEY) yoksa net hata verir.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing OPENAI_API_KEY in environment variables.",
        )
    return OpenAI(api_key=api_key)


def extract_user_text(req: AskRequest) -> str:
    """
    message/question ikisini de destekler. Boşsa '' döner.
    """
    text = (req.message or req.question or "").strip()
    return text


def check_token(x_sanri_token: Optional[str]) -> None:
    """
    Token zorunlu olsun istersen EXPECTED_SANRI_TOKEN tanımla.
    Boş bırakılırsa token kontrolü yapılmaz.
    """
    if not EXPECTED_SANRI_TOKEN:
        return  # token kontrolü kapalı

    if not x_sanri_token or x_sanri_token.strip() != EXPECTED_SANRI_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid x-sanri-token.")


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_sanri_token: Optional[str] = Header(default=None),
):
    # 1) Token kontrolü (opsiyonel)
    check_token(x_sanri_token)

    # 2) Text + session
    user_text = extract_user_text(req)
    session_id = (req.session_id or "default").strip()

    if not user_text:
        return AskResponse(response="", session_id=session_id)

    # 3) System prompt
    mode = (req.mode or "user").strip()
    try:
        system_prompt = build_system_prompt(mode)
    except Exception as e:
        logger.exception("build_system_prompt failed")
        raise HTTPException(status_code=500, detail=f"System prompt error: {str(e)}")

    # 4) OpenAI çağrısı (chat.completions) — responses kullanmıyoruz
    client = get_client()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.4,
            max_tokens=300,
        )
        reply = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        # Burada artık gerçek hata mesajını döndürüyoruz ki 500'ün sebebi saklanmasın.
        logger.exception("OpenAI chat completion failed")
        raise HTTPException(status_code=500, detail=str(e))

    if not reply:
        reply = "Buradayım."

    return AskResponse(response=reply, session_id=session_id)