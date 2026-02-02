import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.rituel_prompt import RITUEL_PROMPT

router = APIRouter(prefix="/rituel-alani", tags=["rituel-alani"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

class AskRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class AskResponse(BaseModel):
    response: str
    session_id: str

@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    messages = [
        {"role":"system","content": RITUEL_PROMPT},
        {"role":"user","content": req.message}
    ]

    try:
        out = client.chat.completions.create(model=MODEL_NAME, messages=messages)
        reply = (out.choices[0].message.content or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not reply:
        reply = "Dur."

    return AskResponse(response=reply, session_id=req.session_id or "default")