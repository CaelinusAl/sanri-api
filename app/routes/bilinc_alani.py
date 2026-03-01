# app/routes/bilinc_alani.py
import os
import re
import time
import uuid
import json
import traceback
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List, Tuple, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from openai import OpenAI

from app.db import get_db

# Module registry (senin projede bu neredeyse oradan import et)
# Eğer sende farklı dosyadaysa bu satırı düzelt.
from app.modules.registry import REGISTRY  # type: ignore

# Prompt version
from app.prompts.system_base import SANRI_PROMPT_VERSION  # type: ignore

# DB models (yoksa None'a düşer)
try:
    from app.models.event import Event  # type: ignore
except Exception:
    Event = None

try:
    from app.models.memory import Memory  # type: ignore
except Exception:
    Memory = None


router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "1200"))

MEM_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))
MEM_TTL = int(os.getenv("SANRI_MEMORY_TTL", "7200"))

MEM: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MEM_TURNS * 2))
LAST_SEEN: Dict[str, float] = {}

MODE_TAG_RE = re.compile(r"^\\s*\\[SANRI[\\s]?MODE\\s*=\\s*([a-zA-Z0-9-]+)\\s*\\]\\s*", re.IGNORECASE)
ALLOWED_GATE_MODES = {"mirror", "dream", "divine", "shadow", "light"}


def ensure_json_obj(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return {"error": "invalid_json", "reason": "not_object", "raw": raw[:800]}
    except Exception:
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                obj = json.loads(raw[start : end + 1])
                if isinstance(obj, dict):
                    return obj
        except Exception:
            pass
        return {"error": "invalid_json", "raw": raw[:800]}


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
    m = MODE_TAG_RE.match(text or "")
    if not m:
        return ("mirror", (text or "").strip())

    mode = (m.group(1) or "mirror").lower().strip()
    if mode not in ALLOWED_GATE_MODES:
        mode = "mirror"

    cleaned = MODE_TAG_RE.sub("", text, count=1).strip()
    return (mode, cleaned)


def safe_domain(req_dict: dict) -> str:
    d = (req_dict.get("domain") or "").strip()
    return d if d else "auto"


def safe_meta(req_dict: dict, context: dict) -> dict:
    return {
        "domain": req_dict.get("domain"),
        "gate_mode": req_dict.get("gate_mode"),
        "persona": req_dict.get("persona"),
        "lang": req_dict.get("lang"),
        "plate": req_dict.get("plate"),
        "context_source": (context or {}).get("source"),
        "context_intent": (context or {}).get("intent"),
        "city_code": (context or {}).get("city_code"),
        "layer": (context or {}).get("layer"),
        "target": (context or {}).get("target"),
        "title": (context or {}).get("title"),
    }


def db_log_event(db: Session, user_id: Optional[str], action: str, domain: str, meta: dict) -> None:
    if Event is None:
        return
    try:
        ev = Event(user_id=user_id, action=action, domain=domain, meta=meta or None)
        db.add(ev)
        db.commit()
    except Exception:
        db.rollback()


def db_save_memory(db: Session, user_id: Optional[str], mem_type: str, context: dict, input_text: str, output_text: str) -> None:
    if Memory is None:
        return
    try:
        m = Memory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=mem_type or "auto",
            context=context or None,
            input_text=input_text or "",
            output_text=output_text or "",
        )
        db.add(m)
        db.commit()
    except Exception:
        db.rollback()


class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"

    domain: Optional[str] = "auto"
    gate_mode: Optional[str] = "mirror"
    persona: Optional[str] = "user"
    plate: Optional[str] = None

    context: Optional[dict] = None
    lang: Optional[str] = None

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


def normalize_req(req: AskRequest, raw_text: str) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    cleaned_text = (raw_text or "").strip()
    tag_mode, cleaned_text = extract_mode_and_clean(cleaned_text)

    domain = (req.domain or "auto").strip() or "auto"
    gate_mode = (req.gate_mode or "mirror").strip().lower() or "mirror"
    persona = (req.persona or "user").strip() or "user"
    plate = (req.plate or "").strip()
    lang = (req.lang or "").strip().lower() or None

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

    ctx = req.context or {}
    if not isinstance(ctx, dict):
        ctx = {}

    return (
        {"domain": domain, "gate_mode": gate_mode, "persona": persona, "plate": plate, "lang": lang},
        cleaned_text,
        ctx,
    )


def _pick_answer(reply_json: Dict[str, Any], out: Dict[str, Any], fallback_lang: str) -> str:
    # 1) module.postprocess cevabı
    a = (out.get("answer") or out.get("response") or "").strip() if isinstance(out, dict) else ""
    if a:
        return a

    # 2) model json cevabı
    a2 = str(reply_json.get("answer") or reply_json.get("response") or "").strip()
    if a2:
        return a2

    # 3) fallback
    return "Buradayım." if fallback_lang == "tr" else "I'm here."


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
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

    req_dict, cleaned_text, ctx_in = normalize_req(req, raw_text)
    domain = safe_domain(req_dict)

    module = REGISTRY.get(domain) or REGISTRY.get("auto")
    if module is None:
        raise HTTPException(status_code=500, detail="Module registry misconfigured (auto missing)")

    # preprocess
    try:
        ctx = module.preprocess(cleaned_text, {**req_dict, "context": ctx_in})
    except TypeError:
        ctx = module.preprocess(cleaned_text, req_dict)

    # build prompts
    try:
        system_prompt = module.build_system(req_dict, ctx)
        user_payload = module.build_user(req_dict, ctx)
    except TypeError:
        system_prompt = module.build_system({**req_dict, "context": ctx_in}, ctx)
        user_payload = module.build_user({**req_dict, "context": ctx_in}, ctx)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages(session_id))
    messages.append({"role": "user", "content": user_payload})

    user_id = None
    meta = safe_meta(req_dict, ctx_in)
    meta["session_id"] = session_id
    meta["token_present"] = bool(x_sanri_token)
    db_log_event(db, user_id, action="ask", domain=domain, meta=meta)

    client = get_client()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        reply_text = (completion.choices[0].message.content or "").strip()
        reply_json = ensure_json_obj(reply_text)
    except Exception as e:
        print("SANRI LLM ERROR")
        print(repr(e))
        print(traceback.format_exc())
        print("PROMPT_VERSION:", SANRI_PROMPT_VERSION)
        print("SESSION:", session_id)
        raise HTTPException(status_code=500, detail="LLM_ERROR: " + str(e))

    # postprocess (dict bekliyoruz)
    try:
        out = module.postprocess(reply_json, req_dict, ctx) or {}
    except TypeError:
        out = module.postprocess(reply_json, req_dict) or {}

    lang = (req_dict.get("lang") or "tr").lower()
    answer = _pick_answer(reply_json, out, "tr" if lang not in ("tr", "en") else lang)

    # in-memory
    remember(session_id, "user", cleaned_text)
    remember(session_id, "assistant", answer)

    # DB memory
    db_save_memory(
        db,
        user_id=None,
        mem_type=domain,
        context={
            "session_id": session_id,
            "domain": domain,
            "gate_mode": req_dict.get("gate_mode"),
            "lang": req_dict.get("lang"),
            "source": (ctx_in or {}).get("source"),
            "intent": (ctx_in or {}).get("intent"),
        },
        input_text=cleaned_text,
        output_text=answer,
    )

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