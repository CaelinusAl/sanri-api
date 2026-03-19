from typing import List, Optional, Any
import json
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


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


def strip_code_fences(raw: str) -> str:
    text = (raw or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return text


def build_ritual_fallback(clean: str, session_id: str) -> dict:
    return {
        "answer": "Sanrı Ritüeli",
        "response": f"Sanrı alanı şunu duydu: {clean}",
        "title": "Bırakış Ritüeli",
        "message": f"İçindeki his görünür oldu: {clean}",
        "steps": [
            "Gözlerini kapat.",
            f"İçinden şu duyguyu çağır: {clean}",
            "Bu hissi yargılamadan izle.",
            "Son nefeste bırak.",
        ],
        "closing": "Taşıdığın şey artık adını aldı. Çözülme başladı.",
        "session_id": session_id,
        "prompt_version": "ritual_fallback_v3",
    }


def generate_live_ritual(client: OpenAI, clean: str, session_id: str) -> dict:
    system_prompt = """
You are Sanrı.

You create short living ritual experiences in Turkish.
Return valid JSON only. No markdown. No code fences.

Schema:
{
  "title": "short ritual title",
  "message": "opening sentence",
  "steps": ["step 1", "step 2", "step 3", "step 4"],
  "closing": "closing sentence"
}

Rules:
- Write in Turkish.
- The ritual should feel intimate, calm, mystical, embodied, and clear.
- Use exactly 4 ritual steps.
- Each step should be short and readable on mobile.
- The opening should feel like entering a living ritual field.
- The closing should feel personal and transformative.
- Do not analyze the user. Create the ritual directly.
- Avoid therapy language and avoid long explanations.
"""

    user_prompt = f"""
User opened a live ritual field with this feeling or sentence:

"{clean}"

Create a living ritual now.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.9,
        max_tokens=500,
    )

    raw = response.choices[0].message.content or ""
    raw = strip_code_fences(raw)

    try:
        data: Any = json.loads(raw)
    except Exception:
        return build_ritual_fallback(clean, session_id)

    title = str(data.get("title") or "").strip()
    message = str(data.get("message") or "").strip()
    closing = str(data.get("closing") or "").strip()
    steps_raw = data.get("steps") or []

    if not isinstance(steps_raw, list):
        return build_ritual_fallback(clean, session_id)

    steps = [str(x).strip() for x in steps_raw if str(x).strip()]

    if not title or not message or not closing or len(steps) < 3:
        return build_ritual_fallback(clean, session_id)

    steps = steps[:4]

    return {
        "answer": title,
        "response": message,
        "title": title,
        "message": message,
        "steps": steps,
        "closing": closing,
        "session_id": session_id,
        "prompt_version": "ritual_live_v3",
    }


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    user_message = (req.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")

    # -------------------------------------------------
    # Live ritual mode
    # -------------------------------------------------
    if user_message.lower().startswith("ritual:"):
        clean = user_message.replace("ritual:", "", 1).strip()
        if not clean:
            clean = "İçimde açılmak isteyen bir alan var"

        try:
            client = get_client()
            return generate_live_ritual(client, clean, req.session_id)
        except Exception:
            return build_ritual_fallback(clean, req.session_id)

    # -------------------------------------------------
    # Default Sanrı mode
    # -------------------------------------------------
    try:
        client = get_client()

        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are Sanrı. You reflect meaning, not answers. Respond in the user's language, briefly and warmly.",
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            temperature=0.8,
            max_tokens=500,
        )

        text = completion.choices[0].message.content or "Sanrı seni duydu."

        return {
            "answer": text,
            "response": text,
            "session_id": req.session_id,
            "prompt_version": "default_v2",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    except Exception:
        fallback = "Sanrı şu an sessizlikte cevap veriyor."

        return {
            "answer": fallback,
            "response": fallback,
            "session_id": req.session_id,
            "prompt_version": "default_fallback_v2",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }