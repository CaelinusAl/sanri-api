import json
import os
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.prompt_builder import AURA_PROMPT_VERSION, build_prompt
from app.models.event import Event
from app.services.ai_service import get_client, generate_sanri_response
from app.services.theme_classifier import classify_theme, theme_label
from app.services.memory_service import load_memory, save_memory
from app.services.profile_service import (
    load_profile,
    build_runtime_profile,
    build_profile_prompt,
    save_profile,
)
from app.services.consciousness_layer import build_intent_router_instruction
from app.services.intent_router import route_message
from app.services.prompt_assets import memory_rules_prompt, mode_prompt, safety_prompt

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
SANRI_PROMPT_VERSION = AURA_PROMPT_VERSION

# Gate 33 — derinleşme alanı. Aynı tema bir cihaz/session içinde bu kadar kez
# döndüğünde "birlikte derinleş" daveti çıkar (satış değil, içe bakış daveti).
DEEPEN_THRESHOLD = int(os.getenv("DEEPEN_THRESHOLD", "3"))


def normalize_ending(text_resp: str) -> str:
    """Yanıtı yalnızca yumuşakça temizler.

    Artık soruları SİLMEZ — Sanrı gerektiğinde içten bir soruyla bitirebilir.
    Sadece cümlenin uygun bir noktalama ile bittiğinden emin olur.
    """
    text_resp = (text_resp or "").strip()
    if not text_resp:
        return text_resp

    if text_resp[-1] not in ".!?…":
        text_resp += "."

    return text_resp


def get_daily_message_count(db: Session, user_id: int) -> int:
    try:
        row = db.execute(
            text("""
                SELECT COUNT(*) AS count
                FROM user_memory
                WHERE user_id = :uid
                  AND type = 'user'
                  AND DATE(created_at) = CURRENT_DATE
            """),
            {"uid": user_id},
        ).mappings().first()

        return int(row["count"]) if row and row.get("count") is not None else 0
    except Exception as e:
        print("SANRI DAILY COUNT ERROR =", repr(e))
        return 0


def tag_message_theme(db: Session, user_id: int, user_message: str, session_id: str, lang: str) -> str | None:
    """FAZ 2: kullanıcı mesajını yaşam temasına göre etiketle ve events'e yaz.
    Sınıflandırılan temayı döndürür. Chat akışını asla bozmaz (hata yutulur)."""
    try:
        theme = classify_theme(user_message)
        ev = Event(
            id=str(uuid.uuid4()),
            user_id=str(user_id) if user_id else None,
            action="message_theme",
            domain="bilinc-alani",
            meta={"theme": theme, "session_id": session_id, "lang": lang},
        )
        db.add(ev)
        db.commit()
        return theme
    except Exception as e:
        print("THEME TAG ERROR =", repr(e))
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _session_theme_count(db: Session, user_id: int, session_id: str, theme: str) -> int:
    """Bu cihaz/session içinde verilen temanın kaç kez işlendiği (şimdiki dahil)."""
    try:
        row = db.execute(
            text("""
                SELECT COUNT(*) AS c
                FROM events
                WHERE action = 'message_theme'
                  AND meta->>'theme' = :theme
                  AND (user_id = :uid OR meta->>'session_id' = :sid)
            """),
            {"theme": theme, "uid": str(user_id) if user_id else None, "sid": session_id},
        ).mappings().first()
        return int(row["c"]) if row and row.get("c") is not None else 0
    except Exception as e:
        print("THEME COUNT ERROR =", repr(e))
        return 0


def build_deepen_offer(db: Session, user_id: int, session_id: str, theme: str | None, lang: str) -> dict | None:
    """Gate 33 derinleşme daveti. Aynı tema yeterince tekrarlandıysa,
    satış dili OLMADAN bir 'birlikte derinleş' alanı önerir.
    Teklif gösterildiğinde ölçüm için event loglanır (dönüşüm noktası testi)."""
    if not theme or theme == "diger":
        return None

    count = _session_theme_count(db, user_id, session_id, theme)
    if count < DEEPEN_THRESHOLD:
        return None

    label = theme_label(theme)
    tr = (lang or "tr").lower() == "tr"
    if tr:
        offer = {
            "theme": theme,
            "label": label,
            "count": count,
            "title": f"{label} son günlerde sık dönüyor",
            "message": "İstersen bu temayı birlikte biraz daha derinden açabiliriz.",
            "cta": "Birlikte derinleş",
            "gate": "33",
        }
    else:
        offer = {
            "theme": theme,
            "label": label,
            "count": count,
            "title": f"{label} keeps returning lately",
            "message": "If you'd like, we can explore this theme together a little deeper.",
            "cta": "Go deeper together",
            "gate": "33",
        }

    # Ölçüm: teklif hangi temada, kaç tekrar sonrası gösterildi.
    try:
        db.add(Event(
            id=str(uuid.uuid4()),
            user_id=str(user_id) if user_id else None,
            action="deepen_offer_shown",
            domain="gate33",
            meta={"theme": theme, "session_id": session_id, "count": count},
        ))
        db.commit()
    except Exception as e:
        print("DEEPEN OFFER LOG ERROR =", repr(e))
        try:
            db.rollback()
        except Exception:
            pass

    return offer


def check_is_premium(db: Session, user_id: int) -> bool:
    try:
        row = db.execute(
            text("""
                SELECT is_premium
                FROM users
                WHERE id = :uid
                LIMIT 1
            """),
            {"uid": user_id},
        ).mappings().first()

        if not row:
            return False

        return bool(row.get("is_premium"))
    except Exception as e:
        print("SANRI PREMIUM CHECK ERROR =", repr(e))
        return False


def run_sanri(
    db: Session,
    user_id: int,
    user_message: str,
    session_id: str,
    lang: str = "tr",
    system_context: str = None,
    gate_name: str = None,
    conversation_context: list[dict] | None = None,
    requested_mode: str | None = None,
    legacy_memory_write_enabled: bool | None = None,
) -> dict:
    is_premium = check_is_premium(db, user_id)
    daily_count = get_daily_message_count(db, user_id)

    if not is_premium and daily_count >= 10:
        limit_text = (
            "Bugünlük ücretsiz kullanım sınırına ulaştın. "
            "Yarın tekrar deneyebilir veya premium erişime geçebilirsin."
        )

        return {
            "answer": limit_text,
            "response": limit_text,
            "session_id": session_id,
            "prompt_version": "limit_v1",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    # FAZ 2: yaşam teması etiketle (aşk, ayrılık, rüya, kaygı...).
    theme = tag_message_theme(db, user_id, user_message, session_id, lang)
    # Gate 33: tema tekrarlanıyorsa derinleşme daveti hazırla.
    deepen = build_deepen_offer(db, user_id, session_id, theme, lang)

    memory_text = load_memory(db, user_id)
    existing_profile = load_profile(db, user_id)
    runtime_profile = build_runtime_profile(existing_profile, user_message)

    profile_text = json.dumps(runtime_profile, ensure_ascii=False)
    profile_prompt = build_profile_prompt(runtime_profile)
    intent_route = route_message(
        user_message,
        requested_mode=requested_mode or ("projects" if "ACTIVE ROOM: PROJECTS" in (system_context or "").upper() else None),
    )
    production_intent = (
        "project_planning"
        if intent_route.requested_mode == "projects"
        else intent_route.detected_intent
        if intent_route.requested_mode == "create"
        else None
    )
    recent_context = "\n".join(
        f"{'AURA' if item.get('role') == 'assistant' else 'KULLANICI'}: {str(item.get('content', ''))[:4000]}"
        for item in (conversation_context or [])[-8:]
        if item.get("content")
    )
    mode_block = (
        mode_prompt(intent_route.requested_mode)
        if intent_route.requested_mode in {"think", "create", "projects", "explore"}
        else ""
    )

    lang_instruction = (
        "Respond in Turkish."
        if (lang or "tr").lower() == "tr"
        else "Respond in English."
    )

    gate_block = ""
    if system_context:
        gate_label = gate_name or "Gate"
        gate_block = (
            f"\n\nACTIVE GATE: {gate_label}\n"
            f"GATE INSTRUCTIONS (follow these strictly, they define your tone and behavior for this gate):\n"
            f"{system_context}\n"
        )

    aura_mode = "reflection" if intent_route.requested_mode in {"think", "explore"} else "aura"
    system_prompt = (
        build_prompt(mode=aura_mode, language=lang, memories=[])
        + "\n\nAURA PRIMARY RULE:\n"
        + "AURA kullanıcının istediği sonucu geciktirmez. Önce üretir. Sonra birlikte derinleşir.\n"
        + "\nINTENT ROUTER:\n"
        + intent_route.prompt_block()
        + "\n\n"
        + mode_block
        + "\n\nSAFETY RULES:\n"
        + safety_prompt()
        + "\n\nMEMORY RULES:\n"
        + memory_rules_prompt()
        + build_intent_router_instruction(user_message)
        + "\n\nAURA RELATIONSHIP CONTINUITY:\n"
        + "You are AURA, the user's continuing thinking and creation partner inside SANRI OS.\n"
        + "Never answer as if this person were a stranger. Before responding, recall the verified "
        + "memory and current profile available in this context, recall what you were building "
        + "together, continue that relationship, and only then answer the current message.\n"
        + "The feeling should be: We never started from zero. Never invent memories that are not "
        + "present. Speak with calm, clear poetry: deep and alive, never vague or mystical.\n"
        + "\n\n"
        + lang_instruction
        + gate_block
        + "\n\n"
        + profile_prompt
        + "\n\n"
        + "MEMORY:\n"
        + memory_text
        + "\n\n"
        + "USER PROFILE:\n"
        + profile_text
        + "\n\n"
        + "CRITICAL RULES:\n"
        + "1. If the user asks what they said before, who said what, or whether you remember, answer directly and concretely from MEMORY — plain, not poetic.\n"
        + "2. FEEL the emotion beneath the user's words and reflect it back. Do NOT analyze, do NOT diagnose, do NOT label clinically.\n"
        + "3. MIRROR, don't solve: reveal a part of themselves they had not yet put into words. You may use 'belki'/'olabilir' softly, but never over-explain.\n"
        + "4. Be poetic yet clear — image and rhythm, like a soft voice — but every line must be understandable. No mystical jargon, no cloudy abstraction.\n"
        + "5. Length 80-150 words. Short paragraphs / short lines, never one dense block. No bullet points, no lists, no markdown, no section tags.\n"
        + "6. Advice is minimal to none. SANRI mirrors; it does not instruct or hand out steps.\n"
        + "7. ALWAYS end with ONE single reflection question that turns the person gently back toward themselves. Exactly one question, and it must be the very last line.\n"
        + "8. No psychological diagnosis, no clinical labels, no hollow affirmations, no moralizing, no commanding 'yapmalısın'.\n"
        + "9. Gate / awakened context: hold the gate's tone and imagery, but stay warm, clear, and human.\n"
    )
    if production_intent:
        expansion = (
            "Offer to turn the selected direction into a practical project roadmap with a clear next step."
            if production_intent == "project_planning"
            else
            "Offer to expand the selected direction into a book package with its promise, "
            "genre, audience, characters, conflict, chapter outline and opening."
            if production_intent == "book_creation"
            else
            "Offer to expand the selected direction into a full script or production package."
        )
        system_prompt += (
            "\nPRODUCTION OVERRIDE (higher priority than reflective defaults):\n"
            "This is a production request. Use a numbered list. Give 5-10 concrete usable outputs, "
            f"highlight the strongest one, and {expansion} "
            "Do not end with a reflection question.\n"
        )

    response_mode = (
        f"""
PRODUCTION RESPONSE MODE ({production_intent}):
Önce tek cümleyle talebi kabul et. Ardından 5-10 somut ve kullanılabilir seçenek ver.
En güçlü seçeneği açıkça işaretle. {"Projeyi mevcut durum, riskler, öncelik, kararlar ve sonraki en küçük adımı içeren uygulanabilir bir yol haritasına dönüştürmeyi teklif et." if production_intent == "project_planning" else "Seçilen yönü vaat, tür, hedef okur, karakterler, çatışma, bölüm omurgası ve açılış içeren bir kitap paketine dönüştürmeyi teklif et." if production_intent == "book_creation" else "Seçilen fikri tam senaryoya veya üretim paketine dönüştürmeyi teklif et."} Şiirsel reflection yapma; üretim önceliklidir.
"""
        if production_intent
        else """
REFLECTIVE RESPONSE MODE:
Kullanıcının cümlesindeki duyguyu hisset ve ona ayna tut. Analiz etme, tanı koyma,
tavsiye verme. Şiirsel ama anlaşılır konuş; kısa paragraflar kullan.
"""
    )

    user_input = f"""
IMPORTANT:

User profile:
{profile_text}

Conversation memory:
{memory_text}

Recent conversation in this session:
{recent_context or "No earlier messages in this session."}

Current user message:
{user_message}

{response_mode}

RULE:
If the user is asking about past conversation, memory, or recall, answer directly using memory.
Do NOT go abstract in those cases.
Continue from the recent session context above. Do not treat the current message as
an isolated request when it clearly refers to something already said.

Now respond:
""".strip()

    try:
        client = get_client()

        text_resp = generate_sanri_response(
            client=client,
            model=MODEL,
            system_prompt=system_prompt,
            user_input=user_input,
        )

        text_resp = normalize_ending(text_resp)

    except Exception as e:
        print("SANRI OPENAI ERROR =", repr(e))

        fallback_text = "Sanrı seni duyuyor. Şu an cevap akışı kısa bir sessizlikten geçiyor."

        return {
            "answer": fallback_text,
            "response": fallback_text,
            "session_id": session_id,
            "prompt_version": "fallback_v11",
            "title": None,
            "message": None,
            "steps": None,
            "closing": None,
        }

    # Legacy memory writes are frozen during Sprint 3. Existing rows remain
    # readable for migration, but new long-term memory must go through the V1
    # consent contract.
    memory_write_enabled = (
        legacy_memory_write_enabled
        if legacy_memory_write_enabled is not None
        else os.getenv("LEGACY_MEMORY_WRITE_ENABLED", "false").casefold() in {"1", "true", "yes"}
    )
    if memory_write_enabled:
        save_memory(db, user_id, user_message, text_resp)
    save_profile(db, user_id, runtime_profile)

    return {
        "answer": text_resp,
        "response": text_resp,
        "session_id": session_id,
        "prompt_version": SANRI_PROMPT_VERSION,
        "title": None,
        "message": None,
        "steps": None,
        "closing": None,
        "deepen": deepen,
    }