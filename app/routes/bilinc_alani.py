# app/routes/bilinc_alani.py
import os
import re
import time
import traceback
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List, Tuple

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.system_base import build_system_prompt, SANRI_PROMPT_VERSION

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "1200"))

# session memory
MEM_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))  # user+assistant turns
MEM_TTL = int(os.getenv("SANRI_MEMORY_TTL", "7200"))    # seconds (2 hours)

# session_id -> deque of (role, content)
MEM: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MEM_TURNS * 2))
LAST_SEEN: Dict[str, float] = {}

# allow frontend tag: [SANRI_MODE=mirror]
MODE_TAG_RE = re.compile(r"^\s*\[SANRI[\s]?MODE\s*=\s*([a-zA-Z0-9-]+)\s*\]\s*", re.IGNORECASE)

ALLOWED_MODES = {"mirror", "dream", "divine", "shadow", "light"}


class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"  # user | test | cocuk

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    response: str
    session_id: str
    prompt_version: str


def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing or empty")
    return OpenAI(api_key=api_key)


def gc_sessions() -> None:
    now = time.time()
    if MEM_TTL <= 0:
        return
    dead = [sid for sid, ts in LAST_SEEN.items() if now - ts > MEM_TTL]
    for sid in dead:
        LAST_SEEN.pop(sid, None)
        MEM.pop(sid, None)


def touch(sid: str) -> None:
    LAST_SEEN[sid] = time.time()


def remember(sid: str, role: str, content: str) -> None:
    if not content:
        return
    MEM[sid].append((role, content))
    touch(sid)


def history_messages(sid: str) -> List[dict]:
    out: List[dict] = []
    for role, content in MEM.get(sid, []):
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def extract_mode_and_clean(text: str) -> Tuple[str, str]:
    """
    Reads optional [SANRI_MODE=...] tag.
    Returns (sanri_mode, cleaned_text).
    """
    m = MODE_TAG_RE.match(text or "")
    if not m:
        return ("mirror", (text or "").strip())

    mode = (m.group(1) or "mirror").lower().strip()
    if mode not in ALLOWED_MODES:
        mode = "mirror"

    cleaned = MODE_TAG_RE.sub("", text, count=1).strip()
    return (mode, cleaned)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    gc_sessions()

    session_id = (req.session_id or "default").strip() or "default"
    raw_text = req.text()

    if not raw_text:
        return AskResponse(response="", session_id=session_id, prompt_version=SANRI_PROMPT_VERSION)

    # 1) Parse SANRI_MODE tag (only as a gentle hint)
    sanri_mode, user_text = extract_mode_and_clean(raw_text)

    # 2) Build system prompt ONLY from system_base (no extra format forcing)
    system_prompt = build_system_prompt(req.mode)

    # 3) If tag exists, we pass it as a subtle first line (NOT a format command)
    if sanri_mode and sanri_mode != "mirror":
        user_text = "(SANRI_MODE: " + sanri_mode + ")\n" + user_text

    # 4) Build messages with memory
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages(session_id))
    messages.append({"role": "user", "content": user_text})

    try:
        client = get_client()

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        reply = (completion.choices[0].message.content or "").strip()

    except Exception as e:
        print("🔥 SANRI LLM ERROR 🔥")
        print(repr(e))
        print(traceback.format_exc())
        print("PROMPT_VERSION:", SANRI_PROMPT_VERSION)
        print("SESSION:", session_id)
        raise HTTPException(status_code=500, detail="LLM_ERROR: " + str(e))

    if not reply:
        reply = "Buradayım."

    # 5) Save memory AFTER success
    remember(session_id, "user", user_text)
    remember(session_id, "assistant", reply)

    return AskResponse(response=reply, session_id=session_id, prompt_version=SANRI_PROMPT_VERSION)