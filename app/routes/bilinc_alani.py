# app/routes/bilinc_alani.py
import os
import re
import time
import traceback
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.system_base import build_system_prompt, SANRI_PROMPT_VERSION

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

# -----------------------
# Config
# -----------------------
MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.6"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

# memory size per session (messages)
MEMORY_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))  # each turn = user+assistant, we store messages
# soft time-to-live in seconds (optional)
MEMORY_TTL = int(os.getenv("SANRI_MEMORY_TTL", "3600"))  # 1 hour

# -----------------------
# In-memory session store
# -----------------------
# { session_id: deque([{role, content, ts}, ...]) }
_session_memory: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=MEMORY_TURNS * 2))
_session_last_seen: Dict[str, float] = {}

# -----------------------
# Schemas
# -----------------------
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

# -----------------------
# Helpers
# -----------------------
def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)

def _cleanup_old_sessions():
    """Best-effort cleanup for long-running process (Railway)."""
    now = time.time()
    if MEMORY_TTL <= 0:
        return
    to_delete = [sid for sid, ts in _session_last_seen.items() if (now - ts) > MEMORY_TTL]
    for sid in to_delete:
        _session_last_seen.pop(sid, None)
        _session_memory.pop(sid, None)

SANRI_MODE_RE = re.compile(r"\[SANRI[\s]?MODE\s*=\s*([a-zA-Z0-9_-]+)\]", re.IGNORECASE)

def extract_sanri_mode_from_text(text: str) -> Optional[str]:
    """Reads [SANRI_MODE=mirror] etc from message."""
    m = _SANRI_MODE_RE.search(text or "")
    if not m:
        return None
    return (m.group(1) or "").strip().lower()

def strip_mode_tag(text: str) -> str:
    """Removes [SANRI_MODE=...] tag from user text to keep it clean."""
    return _SANRI_MODE_RE.sub("", text or "").strip()

def build_messages(session_id: str, system_prompt: str, user_text: str) -> List[dict]:
    """System + memory + new user message"""
    msgs: List[dict] = [{"role": "system", "content": system_prompt}]

    # add memory if exists
    memory = list(_session_memory.get(session_id, []))
    for m in memory:
        # keep strictly role/content
        msgs.append({"role": m["role"], "content": m["content"]})

    msgs.append({"role": "user", "content": user_text})
    return msgs

def remember(session_id: str, role: str, content: str):
    _session_memory[session_id].append({"role": role, "content": content, "ts": time.time()})
    _session_last_seen[session_id] = time.time()

# -----------------------
# Endpoint
# -----------------------
@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    _cleanup_old_sessions()

    session_id = (req.session_id or "default").strip() or "default"
    raw_text = req.text()

    if not raw_text:
        return AskResponse(response="", session_id=session_id, prompt_version=SANRI_PROMPT_VERSION)

    # 1) Extract SANRI_MODE tag if frontend sends it
    sanri_mode_tag = extract_sanri_mode_from_text(raw_text)
    user_text = strip_mode_tag(raw_text)

    # 2) Choose prompt mode: backend mode (user/test/cocuk) + optional sanri_mode_tag as context
    # We DO NOT create a new rigid format here. We just pass tag as a small hint inside user content.
    system_prompt = build_system_prompt(req.mode)

    # subtle hint to model (keeps tone but doesn't force structure)
    if sanri_mode_tag:
        user_text = f"(SANRI_MODE: {sanri_mode_tag})\n{user_text}"

    # 3) Remember user message first (so next turn can reference it even if LLM errors)
    remember(session_id, "user", user_text)

    try:
        client = get_client()

        messages = build_messages(session_id, system_prompt, user_text)

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        reply = (completion.choices[0].message.content or "").strip()
        if not reply:
            reply = "Buradayım."

        remember(session_id, "assistant", reply)

        # Debug log (Railway)
        print(f"[SANRI] ok | session={session_id} | model={MODEL_NAME} | prompt={SANRI_PROMPT_VERSION} | tokens={MAX_TOKENS}")

        return AskResponse(response=reply, session_id=session_id, prompt_version=SANRI_PROMPT_VERSION)

    except Exception as e:
        # Debug logs
        print("🔥 SANRI LLM ERROR 🔥")
        print(repr(e))
        print(traceback.format_exc())
        print("SANRI PROMPT VERSION:", SANRI_PROMPT_VERSION)
        print("SANRI MODE:", req.mode, "TAG:", sanri_mode_tag)

        # remove last remembered user message if you prefer clean state on error:
        # (optional) keep as is, because it helps continuity even after transient errors.

        raise HTTPException(status_code=500, detail=f"LLM_ERROR: {str(e)}")