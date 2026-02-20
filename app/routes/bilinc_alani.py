# app/routes/bilinc_alani.py
import os
import re
import time
import traceback
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List, Tuple, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from app.prompts.system_base import SANRI_PROMPT_VERSION
from app.modules.registry import REGISTRY

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "1200"))

MEM_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))
MEM_TTL = int(os.getenv("SANRI_MEMORY_TTL", "7200"))

MEM: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MEM_TURNS * 2))
LAST_SEEN: Dict[str, float] = {}

MODE_TAG_RE = re.compile(r"^\s*\[SANRI[\s]?MODE\s*=\s*([a-zA-Z0-9-]+)\s*\]\s*", re.IGNORECASE)
ALLOWED_GATE_MODES = {"mirror", "dream", "divine", "shadow", "light"}


class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"

    domain: Optional[str] = "auto"
    gate_mode: Optional[str] = "mirror"
    persona: Optional[str] = "user"
    plate: Optional[str] = None

    mode: Optional[str] = Field(default=None)

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    response: str
    session_id: str
    prompt_version: str

    module: str = "mirror"
    title: str = "Sanrı"
    answer: str = ""
    sections: List[dict] = []
    tags: List[str] = []


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


def remember(sid: str, role: str, content: str) -> None:
    if not content:
        return
    MEM[sid].append((role, content))
    LAST_SEEN[sid] = time.time()


def history_messages(sid: str) -> List[dict]:
    out: List[dict] = []
    for role, content in MEM.get(sid, []):
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def extract_mode_and_clean(text: str) -> Tuple[str, str]:
    m = MODE_TAG_RE.match(text or "")
    if not m:
        return ("mirror", (text or "").strip())

    mode = (m.group(1) or "mirror").lower().strip()
    if mode not in ALLOWED_GATE_MODES:
        mode = "mirror"

    cleaned = MODE_TAG_RE.sub("", text, count=1).strip()
    return (mode, cleaned)


def normalize_req(req: AskRequest, raw_text: str) -> Tuple[Dict[str, Any], str]:
    cleaned_text = (raw_text or "").strip()

    tag_mode, cleaned_text = extract_mode_and_clean(cleaned_text)

    domain = (req.domain or "auto").strip() or "auto"
    gate_mode = (req.gate_mode or "mirror").strip().lower() or "mirror"
    persona = (req.persona or "user").strip() or "user"
    plate = (req.plate or "").strip()

    if req.mode:
        m = str(req.mode).strip().lower()
        if m in ALLOWED_GATE_MODES:
            gate_mode = m
        else:
            persona = str(req.mode).strip()

    if gate_mode == "mirror" and tag_mode and tag_mode != "mirror":
        gate_mode = tag_mode

    if gate_mode not in ALLOWED_GATE_MODES:
        gate_mode = "mirror"

    req_dict = {
        "domain": domain,
        "gate_mode": gate_mode,
        "persona": persona,
        "plate": plate,
    }
    return req_dict, cleaned_text


def enforce_structure(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "GÖZLEM:\n...\n\nKIRILMA NOKTASI:\n...\n\nSEÇİM ALANI:\n...\n\nTEK SORU:\nGerçekten neyi seçiyorsun?"

    sections = ["GÖZLEM", "KIRILMA NOKTASI", "SEÇİM ALANI", "TEK SORU"]
    upper = t.upper()
    if all(s in upper for s in sections):
        return t

    return (
        "GÖZLEM:\n" + t[:240] + "\n\n"
        "KIRILMA NOKTASI:\nBurada görünmeyen bir seçim var.\n\n"
        "SEÇİM ALANI:\nDevam etmek ya da yeniden kurmak.\n\n"
        "TEK SORU:\nGerçekten neyi seçiyorsun?"
    )


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    gc_sessions()

    session_id = (req.session_id or "default").strip() or "default"
    raw_text = req.text()

    if not raw_text:
        return AskResponse(
            response="",
            answer="",
            session_id=session_id,
            prompt_version=SANRI_PROMPT_VERSION,
            module="mirror",
            title="Sanrı",
            sections=[],
            tags=[],
        )

    req_dict, cleaned_text = normalize_req(req, raw_text)

    domain = req_dict["domain"]
    module = REGISTRY.get(domain) or REGISTRY.get("auto")
    if module is None:
        raise HTTPException(status_code=500, detail="Module registry misconfigured (auto missing)")

    ctx = module.preprocess(cleaned_text, req_dict)
    system_prompt = module.build_system(req_dict, ctx)
    user_payload = module.build_user(req_dict, ctx)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages(session_id))
    messages.append({"role": "user", "content": user_payload})

    client = get_client()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        reply = (completion.choices[0].message.content or "").strip()
        reply = enforce_structure(reply)
    except Exception as e:
        print("🔥 SANRI LLM ERROR 🔥")
        print(repr(e))
        print(traceback.format_exc())
        print("PROMPT_VERSION:", SANRI_PROMPT_VERSION)
        print("SESSION:", session_id)
        raise HTTPException(status_code=500, detail="LLM_ERROR: " + str(e))

    if not reply:
        reply = "Buradayım."

    out = module.postprocess(reply, req_dict, ctx) or {}
    answer = (out.get("answer") or reply).strip()

    remember(session_id, "user", user_payload)
    remember(session_id, "assistant", reply)

    return AskResponse(
        response=answer,
        answer=answer,
        session_id=session_id,
        prompt_version=SANRI_PROMPT_VERSION,
        module=str(out.get("module") or domain),
        title=str(out.get("title") or "Sanrı"),
        sections=list(out.get("sections") or []),
        tags=list(out.get("tags") or []),
    )
