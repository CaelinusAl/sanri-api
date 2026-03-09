from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class AskRequest(BaseModel):
    message: str
    session_id: str = "default"
    lang: str = "tr"


class AskResponse(BaseModel):
    answer: str
    response: str
    session_id: str
    prompt_version: str


def get_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_KEY_MISSING")
    return OpenAI(api_key=key)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id missing")

    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")

    # Ritüel modu
    if message.lower().startswith("ritual:"):
        clean = message.replace("ritual:", "", 1).strip()

        return {
            "answer": "Sanrı Ritüeli",
            "response": (
                f"Gözlerini kapat.\n"
                f"İçinden şu duyguyu çağır: {clean}\n"
                f"Bu hissi yargılamadan izle.\n"
                f"Son nefeste bırak."
            ),
            "session_id": req.session_id,
            "prompt_version": "ritual_v1",
        }

    client = get_client()

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are Sanrı. You reflect meaning, not answers.",
            },
            {
                "role": "user",
                "content": message,
            },
        ],
    )

    text = completion.choices[0].message.content or "Sanrı seni duydu."

    return {
        "answer": text,
        "response": text,
        "session_id": req.session_id,
        "prompt_version": "default_v1",
    }