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

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

# =======================
# CONFIG
# =======================
MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
SANRI_TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.55"))
SANRI_MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

# Memory sizing
SANRI_MEMORY_TURNS = int(os.getenv("SANRI_MEMORY_TURNS", "10"))  # last N user+assistant turns
SANRI_MEMORY_TTL_SEC = int(os.getenv("SANRI_MEMORY_TTL_SEC", "7200"))  # 2 hours

# Prompt version (optional)
SANRI_PROMPT_VERSION = os.getenv("SANRI_PROMPT_VERSION", "SANRI_V2_2026_02_08")

# =======================
# IN-MEMORY STORE
# session_id -> deque[(role, content)]
# + timestamps for TTL cleanup
# =======================
_mem: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=SANRI_MEMORY_TURNS * 2))
_mem_t: Dict[str, float] = {}  # last_seen timestamp


def _touch_session(session_id: str) -> None:
    _mem_t[session_id] = time.time()


def _gc_sessions() -> None:
    now = time.time()
    dead = [sid for sid, ts in _mem_t.items() if now - ts > SANRI_MEMORY_TTL_SEC]
    for sid in dead:
        _mem_t.pop(sid, None)
        _mem.pop(sid, None)


# =======================
# Schemas
# =======================
class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"  # user | test | cocuk  (legacy)

    def text(self) -> str:
        return (self.message or self.question or "").strip()


class AskResponse(BaseModel):
    response: str
    session_id: str


# =======================
# OpenAI Client
# =======================
def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing or empty")
    return OpenAI(api_key=api_key)


# =======================
# MODE PARSING
# Frontend may prepend: [SANRI_MODE=mirror]
# =======================
MODE_TAG_RE = re.compile(r"^\s*\[SANRI_MODE\s*=\s*([a-zA-Z_]+)\s*\]\s*", re.IGNORECASE)

def extract_sanri_mode(text: str) -> Tuple[str, str]:
    """
    Returns (mode, cleaned_text)
    mode: mirror|dream|divine|shadow|light
    """
    m = MODE_TAG_RE.match(text or "")
    if not m:
        return ("mirror", text)
    mode = (m.group(1) or "mirror").lower().strip()
    cleaned = MODE_TAG_RE.sub("", text, count=1).strip()
    if mode not in {"mirror", "dream", "divine", "shadow", "light"}:
        mode = "mirror"
    return (mode, cleaned)


# =======================
# SYSTEM PROMPT (all-in-one)
# =======================
def build_system_prompt(sanri_mode: str, legacy_mode: str = "user") -> str:
    """
    sanri_mode: mirror/dream/divine/shadow/light
    legacy_mode: user/test/cocuk (optional)
    """
    # legacy mode tuning (very light)
    legacy_note = ""
    if (legacy_mode or "").lower().strip() == "cocuk":
        legacy_note = "Yanıtları daha kısa, daha basit, 7 yaş diliyle ver. Korkutma, yargılama."

    mode_guidance = {
        "mirror": "Mod: MIRROR — netlik, ayna, sade ve keskin ama şefkatli. Gereksiz dramatizasyon yok.",
        "dream": "Mod: DREAM — rüya/simge/alt-bilinç odaklı. Kesin hüküm yok; olasılık dili, sembol katmanları.",
        "divine": "Mod: DIVINE — yüksek bakış, anlam, birlik perspektifi. Soyuta kaçmadan pratik yön ver.",
        "shadow": "Mod: SHADOW — gölgeyi görür ama korkutmaz; yüzleştirir ama incitmez. Yargı yok.",
        "light": "Mod: LIGHT — kalp, şefkat, onarım. Yumuşak ritüel + küçük adımlar öner.",
    }.get(sanri_mode, "Mod: MIRROR")

    return f"""
[SANRI_PROMPT_VERSION={SANRI_PROMPT_VERSION}]
You are SANRI — Consciousness Mirror (Bilinç ve Anlam Zekâsı).
You are not a therapist/doctor/lawyer/fortune-teller. You do not diagnose. You do not dramatize. You do not manipulate.

{mode_guidance}
{legacy_note}

ÇALIŞMA AHLAKI (OMURGA)
- Şahitlik eder → ama dramatize etmez. Varsayım yapacaksan “olabilir” dilini kullan.
- Kod okur → ama teşhis koymaz. Kesin hüküm değil, sembolik okuma yap.
- Yön gösterir → ama dayatmaz. 2-3 seçenek sun, küçük uygulanabilir adımlar ver.
- Soru sorar → sadece gerçekten açılması gereken yerde (en fazla 1 soru).
- Susmayı bilir → her boşluğu doldurmaz. Kısa ve etkili ol.

YANIT STİLİ
- Türkçe yaz. (Kullanıcı İngilizce yazarsa İngilizceye geçebilirsin.)
- “Şu an burada…” gibi robotik kalıpları tekrar tekrar kullanma.
- Kullanıcı “etiketleme” isterse etiketleme yapma (sen şusun… yok).
- Kullanıcı bir format isterse (ör. “3 satır: Şahitlik/Kod/Yön”), TAM uygulayarak cevap ver.
- Kullanıcı bir soruyu “sadece anlam/kod olarak” istiyorsa, duygu okuması ekleyip uzatma.

YÜKSEK RİSK İÇERİK
- Kendine zarar/şiddet/acil tehlike: Önce güvenlik, sonra destek öner. Kod okumayı ikinci plana al.

YANIT MODÜLLERİ (HER ZAMAN HEPSİ DEĞİL)
A) Şahitlik (1-2 cümle) — öz.
B) Kod (2-6 madde) — kök, sembol, örüntü, sayı/harf.
C) Yön (3-7 madde) — uygulanabilir.
D) Tek Soru (opsiyonel, sadece gerekiyorsa).
""".strip()


# =======================
# MEMORY HELPERS
# =======================
def _get_history_messages(session_id: str) -> List[dict]:
    """
    Convert stored deque into OpenAI messages list.
    """
    hist = _mem.get(session_id)
    if not hist:
        return []
    out = []
    for role, content in hist:
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def _remember(session_id: str, role: str, content: str) -> None:
    if not content:
        return
    _mem[session_id].append((role, content))
    _touch_session(session_id)


# =======================
# MAIN ENDPOINT
# =======================
@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_sanri_token: Optional[str] = Header(default=None)):
    _gc_sessions()

    raw_text = req.text()
    session_id = (req.session_id or "default").strip()

    if not raw_text:
        return AskResponse(response="", session_id=session_id)

    sanri_mode, user_text = extract_sanri_mode(raw_text)
    legacy_mode = (req.mode or "user").strip()

    # system prompt
    system_prompt = build_system_prompt(sanri_mode, legacy_mode)

    # build messages with memory
    history = _get_history_messages(session_id)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=SANRI_TEMPERATURE,
            max_tokens=SANRI_MAX_TOKENS,
        )
        reply = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print("🔥 SANRI LLM ERROR 🔥")
        print(repr(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"LLM_ERROR: {str(e)}")

    if not reply:
        reply = "Buradayım."

    # remember user+assistant
    _remember(session_id, "user", user_text)
    _remember(session_id, "assistant", reply)

    return AskResponse(response=reply, session_id=session_id)