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
        raise HTTPException(500, "OPENAI_KEY_MISSING")
    return OpenAI(api_key=key)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_user_id: str = Header(None)):

    if not x_user_id:
        raise HTTPException(400, "X-User-Id missing")

    client = get_client()

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are Sanrı. You reflect meaning, not answers."
            },
            {
                "role": "user",
                "content": req.message
            }
        ],
        temperature=0.7,
        max_tokens=600,
    )

    text = completion.choices[0].message.content or ""

    return AskResponse(
        answer=text,
        response=text,
        session_id=req.session_id,
        prompt_version="core"
    )