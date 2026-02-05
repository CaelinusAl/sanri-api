[12:20, 05.02.2026] Celine River: export default async function handler(req, res) {
  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });

  try {
    const { message = "", mode = "user" } = req.body || {};
    const userText = String(message || "").trim();
    if (!userText) return res.status(200).json({ response: "" });

    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) throw new Error("OPENAI_API_KEY missing");

    const SYSTEM = `
You are SANRI.
SANRI is not a teacher. Not a healer. Not a savio…
[12:39, 05.02.2026] Celine River: from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from openai import OpenAI
from app.prompts.system_base import build_system_prompt

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"

class AskResponse(BaseModel):
    response: str
    session_id: str

def get_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=key)

@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    text = (req.message or req.question or "").strip()
    if not text:
        return AskResponse(response="", session_id=req.session_id)

    client = get_client()
    system_prompt = build_system_prompt(req.mode)

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.4,
            max_tokens=300,
        )
        reply = completion.choices[0].message.content or "Buradayım."
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AskResponse(response=reply, session_id=req.session_id)