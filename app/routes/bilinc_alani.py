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
from app.services.usage import check_and_increment

# registry + prompt version
from app.modules.registry import REGISTRY  # type: ignore
from app.prompts.system_base import SANRI_PROMPT_VERSION  # type: ignore

# optional DB models
try:
    from app.models.event import Event  # type: ignore
except Exception:
    Event = None

try:
    from app.models.memory import Memory  # type: ignore
except Exception:
    Memory = None


router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

MEM_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))
MEM_TTL = int(os.getenv("SANRI_MEMORY_TTL", "7200"))

SANRI_DEBUG = (os.getenv("SANRI_DEBUG") or "").strip().lower() in ("1", "true", "yes")

# in-memory history (per session_id)
MEM: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MEM_TURNS * 2))
LAST_SEEN: Dict[str, float] = {}

MODE_TAG_RE = re.compile(r"^\s*\[SANRI[\s]?MODE\s*=\s*([a-zA-Z0-9-]+)\s*\]\s*", re.IGNORECASE)
ALLOWED_GATE_MODES = {"mirror", "dream", "divine", "shadow", "light"}


# ----------------------------
# Helpers
# ----------------------------
def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return str(x)
    except Exception:
        return ""


def ensure_json_obj(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()

    # allow json ... 
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    # try full parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return {"error": "invalid_json", "reason": "not_object", "raw": raw[:800]}
    except Exception:
        # try extract { ... }
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
        raise HTTPException(status_code=500, detail={"code": "OPENAI_KEY_MISSING"})
    # Not: proxies hatası koddan değil, openai/httpx sürümünden gelir.
    # Burada explicit proxies vermiyoruz.
    return OpenAI(api_key=api_key, timeout=60)


def gc_sessions() -> None:
    if MEM_TTL <= 0:
        return
    now = time.time()
    dead = [sid for sid, ts in LAST_SEEN.items() if now - ts > MEM_TTL]
    for sid in dead:
        LAST_SEEN.pop(sid, None)
        MEM.pop(sid, None)


def remember(sid: str, role: str, content: str) -> None:
    c = (content or "").strip()
    if not c:
        return
    MEM[sid].append((role, c))
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


def normalize_req(req: "AskRequest", raw_text: str) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    cleaned_text = (raw_text or "").strip()
    tag_mode, cleaned_text = extract_mode_and_clean(cleaned_text)

    domain = (req.domain or "auto").strip() or "auto"
    gate_mode = (req.gate_mode or "mirror").strip().lower() or "mirror"
    persona = (req.persona or "user").strip() or "user"
    plate = (req.plate or "").strip()
    lang = (req.lang or "").strip().lower() or None

    # legacy: mode
    if req.mode:
        m = _safe_str(req.mode).strip().lower()
        if m in ALLOWED_GATE_MODES:
            gate_mode = m
        else:
            persona = _safe_str(req.mode).strip()

    if gate_mode == "mirror" and tag_mode and tag_mode != "mirror":
        gate_mode = tag_mode

    if gate_mode not in ALLOWED_GATE_MODES:
        gate_mode = "mirror"

    ctx = req.context or {}
    if not isinstance(ctx, dict):
        ctx = {}

    req_dict = {"domain": domain, "gate_mode": gate_mode, "persona": persona, "plate": plate, "lang": lang}
    return req_dict, cleaned_text, ctx


def pick_answer(reply_json: Dict[str, Any], out: Any, lang: str) -> str:
    # 1) module.postprocess
    if isinstance(out, dict):
        a = _safe_str(out.get("answer") or out.get("response")).strip()
        if a:
            return a

    # 2) model json
    a2 = _safe_str(reply_json.get("answer") or reply_json.get("response")).strip()
    if a2:
        return a2

    return "Buradayım." if lang == "tr" else "I'm here."


def safe_meta(req_dict: dict, ctx: dict, session_id: str, token_present: bool) -> dict:
    ctx = ctx or {}
    return {
        "session_id": session_id,
        "token_present": bool(token_present),
        "domain": req_dict.get("domain"),
        "gate_mode": req_dict.get("gate_mode"),
        "persona": req_dict.get("persona"),
        "lang": req_dict.get("lang"),
        "plate": req_dict.get("plate"),
        "context_source": ctx.get("source"),
        "context_intent": ctx.get("intent"),
        "city_code": ctx.get("city_code"),
        "layer": ctx.get("layer"),
        "target": ctx.get("target"),
        "title": ctx.get("title"),
    }


def db_log_event(db: Session, action: str, domain: str, meta: dict) -> None:
    if Event is None:
        return
    try:
        ev = Event(user_id=None, action=action, domain=domain, meta=meta or None)
        db.add(ev)
        db.commit()
    except Exception:
        db.rollback()


def db_save_memory(db: Session, mem_type: str, context: dict, input_text: str, output_text: str) -> None:
    if Memory is None:
        return
    try:
        m = Memory(
            id=str(uuid.uuid4()),
            user_id=None,
            type=mem_type or "auto",
            context=context or None,
            input_text=input_text or "",
            output_text=output_text or "",
        )
        db.add(m)
        db.commit()
    except Exception:
        db.rollback()


# ----------------------------
# Schemas
# ----------------------------
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

    # legacy
    mode: Optional[str] = Field(default=None)

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    response: str
    answer: str
    session_id: str
    prompt_version: str
    module: str = "mirror"
    title: str = "Sanrı"
    sections: List[dict] = []
    tags: List[str] = []


# ----------------------------
# Endpoint
# ----------------------------
@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_user_id: Optional[str] = Header(default=None),
    x_sanri_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Guarantees:
    - Always returns JSON (even on crash)
    - Never calls .strip() on dict
    - Registry/module failures degrade gracefully
    """
    try:
        gc_sessions()

        # header required
        if not x_user_id:
            raise HTTPException(status_code=400, detail={"code": "X_USER_ID_MISSING", "message": "X-User-Id missing"})

        session_id = _safe_str(req.session_id or "default").strip() or "default"
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

        # LIMIT (one time)
        try:
            usage = check_and_increment(db, _safe_str(x_user_id))
        except Exception:
            usage = {"ok": True, "role": "free", "used": 0, "limit": 47}

        if not usage.get("ok", True):
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "LIMIT_REACHED",
                    "role": usage.get("role", "free"),
                    "used": usage.get("used", 0),
                    "limit": usage.get("limit", 47),
                    "message_tr": "Günlük limit doldu. Elite Katman ile sınırsız erişim açılır.",
                    "message_en": "Daily limit reached. Elite unlocks unlimited access.",
                },
            )

        req_dict, cleaned_text, ctx_in = normalize_req(req, raw_text)
        domain = _safe_str(req_dict.get("domain") or "auto").strip() or "auto"

        module = REGISTRY.get(domain) or REGISTRY.get("auto")
        if module is None:
            # hard fallback
            answer = "Buradayım." if (req_dict.get("lang") or "tr") != "en" else "I'm here."
            remember(session_id, "user", cleaned_text)
            remember(session_id, "assistant", answer)
            return AskResponse(
                response=answer,
                answer=answer,
                session_id=session_id,
                prompt_version=SANRI_PROMPT_VERSION,
                module="auto",
                title="Sanrı",
                sections=[],
                tags=["fallback_registry"],
            )

        # preprocess
        try:
            ctx = module.preprocess(cleaned_text, {**req_dict, "context": ctx_in})
        except TypeError:
            ctx = module.preprocess(cleaned_text, req_dict)

        # prompts
        try:
            system_prompt = module.build_system(req_dict, ctx)
            user_payload = module.build_user(req_dict, ctx)
        except TypeError:
            system_prompt = module.build_system({**req_dict, "context": ctx_in}, ctx)
            user_payload = module.build_user({**req_dict, "context": ctx_in}, ctx)

        system_prompt_s = _safe_str(system_prompt)
        user_payload_s = _safe_str(user_payload)

        messages = [{"role": "system", "content": system_prompt_s}]
        messages.extend(history_messages(session_id))
        messages.append({"role": "user", "content": user_payload_s})

        # log event (best-effort)
        try:
            meta = safe_meta(req_dict, ctx_in, session_id=session_id, token_present=bool(x_sanri_token))
            db_log_event(db, action="ask", domain=domain, meta=meta)
        except Exception:
            pass

        # LLM call
        client = get_client()
        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            reply_raw = completion.choices[0].message.content
            reply_text = json.dumps(reply_raw, ensure_ascii=False) if isinstance(reply_raw, (dict, list)) else str(reply_raw or "").strip()
            reply_json = ensure_json_obj(reply_text)
        except HTTPException:
            raise
        except Exception as e:
            detail = {
                "code": "LLM_ERROR",
                "message": str(e),
                "model": MODEL_NAME,
            }
            if SANRI_DEBUG:
                detail["trace"] = traceback.format_exc()[-3500:]
            raise HTTPException(status_code=500, detail=detail)

        # postprocess
        try:
            out = module.postprocess(reply_json, req_dict, ctx) or {}
        except TypeError:
            out = module.postprocess(reply_json, req_dict) or {}
        except Exception:
            out = {}

        lang = (_safe_str(req_dict.get("lang")) or "tr").lower()
        if lang not in ("tr", "en"):
            lang = "tr"

        answer = pick_answer(reply_json, out, lang)

        # memory
        remember(session_id, "user", cleaned_text)
        remember(session_id, "assistant", answer)

        # db memory (best-effort)
        try:
            db_save_memory(
                db,
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
        except Exception:
            pass

        return AskResponse(
            response=answer,
            answer=answer,
            session_id=session_id,
            prompt_version=SANRI_PROMPT_VERSION,
            module=_safe_str((out or {}).get("module") or domain),
            title=_safe_str((out or {}).get("title") or "Sanrı"),
            sections=list((out or {}).get("sections") or []),
            tags=list((out or {}).get("tags") or []),
        )

    except HTTPException:
        # FastAPI will serialize to JSON
        raise
    except Exception as e:
        # NEVER return plain text error
        detail = {"code": "UNHANDLED", "message": str(e)}
        if SANRI_DEBUG:
            detail["trace"] = traceback.format_exc()[-3500:]
        raise HTTPException(status_code=500, detail=detail)