# app/routes/bilinc_alani.py
import os
import re
import time
import traceback
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List, Tuple, Any
from app.modules.registry import REGISTRY

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from app.prompts.system_base import SANRI_PROMPT_VERSION


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

# legacy allow frontend tag: [SANRI_MODE=mirror]
MODE_TAG_RE = re.compile(r"^\s*\[SANRI[\s]?MODE\s*=\s*([a-zA-Z0-9-]+)\s*\]\s*", re.IGNORECASE)
ALLOWED_GATE_MODES = {"mirror", "dream", "divine", "shadow", "light"}


class AskRequest(BaseModel):
    # user input
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"

    # ✅ NEW: gerçek modül seçimi
    domain: Optional[str] = "auto"           # awakened_cities | ritual_space | library | ...
    gate_mode: Optional[str] = "mirror"      # mirror | dream | divine | shadow | light

    # ✅ NEW: system persona (eski req.mode gibi)
    persona: Optional[str] = "user"          # user | test | cocuk

    # ✅ OPTIONAL: awakened_cities için hızlı sinyal
    plate: Optional[str] = None              # "34" gibi

    # ⚠️ BACKWARD COMPAT:
    # Eski client'lar "mode" alanını yolluyor olabilir.
    # - Eğer "mirror/dream/..." yolluyorsa gate_mode gibi alınır
    # - Eğer "user/test/cocuk" yolluyorsa persona gibi alınır
    mode: Optional[str] = Field(default=None)

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    # backward compatibility
    response: str
    session_id: str
    prompt_version: str

    # ✅ NEW structured output
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
    Legacy: Reads optional [SANRI_MODE=...] tag.
    Returns (sanri_mode, cleaned_text).
    """
    m = MODE_TAG_RE.match(text or "")
    if not m:
        return ("mirror", (text or "").strip())

    mode = (m.group(1) or "mirror").lower().strip()
    if mode not in ALLOWED_GATE_MODES:
        mode = "mirror"

    cleaned = MODE_TAG_RE.sub("", text, count=1).strip()
    return (mode, cleaned)


def normalize_req(req: AskRequest, raw_text: str) -> Tuple[Dict[str, Any], str]:
    """
    Normalize inputs across new + old clients.
    Returns (req_dict, cleaned_text)
    """
    cleaned_text = (raw_text or "").strip()

    # legacy tag in text
    tag_mode, cleaned_text2 = extract_mode_and_clean(cleaned_text)
    cleaned_text = cleaned_text2

    # start with request fields
    domain = (req.domain or "auto").strip() or "auto"
    gate_mode = (req.gate_mode or "mirror").strip().lower() or "mirror"
    persona = (req.persona or "user").strip() or "user"
    plate = (req.plate or "").strip()

    # backward compat: req.mode
    if req.mode:
        m = str(req.mode).strip().lower()
        if m in ALLOWED_GATE_MODES:
            gate_mode = m
        else:
            persona = str(req.mode).strip()  # user/test/cocuk vb.

    # if gate_mode not explicitly set but tag exists, use tag
    # (only if gate_mode is default mirror)
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

    # ✅ Normalize all inputs
    req_dict, cleaned_text = normalize_req(req, raw_text)

    # ✅ Choose module by domain
    domain = req_dict["domain"]
    module = REGISTRY.get(domain) or REGISTRY.get("auto")
    if module is None:
        raise HTTPException(status_code=500, detail="Module registry misconfigured (auto missing)")

    # ✅ Module preprocess → system/user prompts
    ctx = module.preprocess(cleaned_text, req_dict)
    system_prompt = module.build_system(req_dict, ctx)
    user_payload = module.build_user(req_dict, ctx)

    # ✅ Build messages with memory
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages(session_id))
    messages.append({"role": "user", "content": user_payload})

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        reply = (completion.choices[0].message.content or "").strip()

        def enforce_structure(text: str) -> str:
            sections = ["GÖZLEM", "KIRILMA NOKTASI", "SEÇİM ALANI", "TEK SORU"]
            missing = [s for s in sections if s not in (text or "").upper()]
            if not missing:
                return text

            return (
                "GÖZLEM:\n" + (text or "")[:200] + "\n\n"
                "KIRILMA NOKTASI:\nBurada görünmeyen bir seçim var.\n\n"
                "SEÇİM ALANI:\nDevam etmek ya da yeniden kurmak.\n\n"
                "TEK SORU:\nGerçekten neyi seçiyorsun?"
            )

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

    # ✅ Postprocess per module (structured response)
    out = module.postprocess(reply, req_dict, ctx) or {}
    answer = (out.get("answer") or reply).strip()

    # ✅ Save memory AFTER success
    remember(session_id, "user", user_payload)
    remember(session_id, "assistant", reply)

    return AskResponse(
        response=answer, # backward compatibility
        answer=answer,
        session_id=session_id,
        prompt_version=SANRI_PROMPT_VERSION,
        module=str(out.get("module") or domain),
        title=str(out.get("title") or "Sanrı"),
        sections=list(out.get("sections") or []),
        tags=list(out.get("tags") or []),
    )
