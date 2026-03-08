# app/routes/bilinc_alani.py

import os
import time
import uuid
from collections import defaultdict, deque
from typing import Optional, Deque, Dict, List, Tuple, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from openai import OpenAI

from app.db import get_db
from app.services.usage import check_and_increment
from app.services.memory import get_user_memory
from app.services.insight_engine import build_user_insight
from app.services.memory_state_engine import build_memory_state
from app.services.memory_engine import build_memory_summary
from app.services.personality_engine import build_personality
from app.services.memory_evolution_engine import evolve_memory
from app.services.soul_engine import build_soul_layer
from app.services.sanri_consciousness_engine import detect_consciousness, build_consciousness_layer
from app.services.intuition_engine import detect_intuition_signal, build_intuition_layer

from app.modules.registry import REGISTRY
from app.prompts.system_base import SANRI_PROMPT_VERSION


router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])


MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

MEM_TURNS = 10
MEM_TTL = 7200

MEM: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MEM_TURNS * 2))
LAST_SEEN: Dict[str, float] = {}


# ------------------------------------------------
# Helpers
# ------------------------------------------------

def get_client():
    key = os.getenv("OPENAI_API_KEY")

    if not key:
        raise HTTPException(500, "OPENAI_KEY_MISSING")

    return OpenAI(api_key=key)


def remember(session_id, role, content):

    if not content:
        return

    MEM[session_id].append((role, content))
    LAST_SEEN[session_id] = time.time()


def history_messages(session_id):

    out = []

    for role, text in MEM.get(session_id, []):
        out.append(
            {
                "role": role,
                "content": text,
            }
        )

    return out


def gc_sessions():

    now = time.time()

    dead = [k for k, v in LAST_SEEN.items() if now - v > MEM_TTL]

    for sid in dead:
        MEM.pop(sid, None)
        LAST_SEEN.pop(sid, None)


# ------------------------------------------------
# Schemas
# ------------------------------------------------

class AskRequest(BaseModel):

    message: Optional[str] = None
    question: Optional[str] = None

    session_id: Optional[str] = "default"

    domain: Optional[str] = "auto"
    gate_mode: Optional[str] = "mirror"

    persona: Optional[str] = "user"

    context: Optional[dict] = None

    lang: Optional[str] = None

    def text(self):

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

    insight: Optional[dict] = None


# ------------------------------------------------
# Endpoint
# ------------------------------------------------

@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):

    try:

        gc_sessions()

        if not x_user_id:
            raise HTTPException(400, "X-User-Id missing")

        session_id = req.session_id or "default"
        text_input = req.text()

        if not text_input:

            return AskResponse(
                response="",
                answer="",
                session_id=session_id,
                prompt_version=SANRI_PROMPT_VERSION,
            )

        usage = {"ok": True}
        if not usage.get("ok", True):

            raise HTTPException(
                402,
                detail={"code": "LIMIT_REACHED"},
            )

        domain = req.domain or "auto"

        module = REGISTRY.get(domain) or REGISTRY.get("auto")

        if module is None:

            answer = "Buradayım."

            remember(session_id, "user", text_input)
            remember(session_id, "assistant", answer)

            return AskResponse(
                response=answer,
                answer=answer,
                session_id=session_id,
                prompt_version=SANRI_PROMPT_VERSION,
            )

        ctx = {}

        try:
            ctx = module.preprocess(text_input, {})
        except Exception:
            ctx = {}

        # ------------------------------------------------
        # MEMORY
        # ------------------------------------------------

        memory_summary = {}
        memory_evolution = {}
        user_memory = []

        try:

            user_memory = get_user_memory(db, int(x_user_id))

            if isinstance(user_memory, list):

                memory_summary = build_memory_summary(user_memory)
                memory_evolution = evolve_memory(user_memory)

                consciousness = detect_consciousness(user_memory)
                consciousness_layer = build_consciousness_layer(consciousness)

                ctx["consciousness"] = consciousness
                ctx["consciousness_layer"] = consciousness_layer

        except Exception:

            consciousness = "unknown"

        ctx["memory_summary"] = memory_summary
        ctx["memory_evolution"] = memory_evolution

        # ------------------------------------------------
        # USER INSIGHT
        # ------------------------------------------------

        insight = None

        try:
            insight = build_user_insight(db, int(x_user_id))
        except Exception:
            pass

        # ------------------------------------------------
        # INTUITION
        # ------------------------------------------------

        intuition_signal = detect_intuition_signal(user_memory, text_input)
        intuition_layer = build_intuition_layer(intuition_signal)

        ctx["intuition_signal"] = intuition_signal
        ctx["intuition_layer"] = intuition_layer

        # ------------------------------------------------
        # SYSTEM PROMPT
        # ------------------------------------------------

        system_prompt = module.build_system({}, ctx)

        system_prompt += "\n\nSANRI MEMORY EVOLUTION:\n" + str(memory_evolution)

        personality_layer = build_personality(memory_summary, insight)
        soul_layer = build_soul_layer(memory_summary, insight)

        system_prompt += "\n\nSANRI SOUL:\n" + soul_layer
        system_prompt += "\n\nSANRI PERSONALITY:\n" + personality_layer
        system_prompt += "\n\nSANRI CONSCIOUSNESS:\n" + ctx.get("consciousness_layer", "")
        system_prompt += "\n\nSANRI INTUITION:\n" + intuition_layer

        user_payload = module.build_user({}, ctx)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_messages(session_id))
        messages.append({"role": "user", "content": user_payload})

        client = get_client()

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        reply = completion.choices[0].message.content or ""
        answer = reply.strip()

        remember(session_id, "user", text_input)
        remember(session_id, "assistant", answer)

        try:
            pass
        except Exception:
            pass
        return AskResponse(
            response=answer,
            answer=answer,
            session_id=session_id,
            prompt_version=SANRI_PROMPT_VERSION,
            module=domain,
            title="Sanrı",
            sections=[],
            tags=[
                f"intuition:{intuition_signal}",
                f"consciousness:{ctx.get('consciousness', 'unknown')}",
            ],
            insight=insight,
        )

    except Exception as e:

        raise HTTPException(
            500,
            detail={
                "code": "SANRI_CRASH",
                "error": str(e),
            },
        )
        