from uuid import uuid4
from pathlib import Path

from app.services.prompt_builder import AURA_PROMPT_VERSION, build_prompt
from app.services.rate_limit import enforce_rate_limit
from app.services.aura_reports import extract_aura_reports, extract_reflection_after_action
from app.services.consciousness_layer import (
    ConsciousnessContext,
    build_consciousness_instruction,
    build_intent_router_instruction,
    detect_production_intent,
)


def test_aura_prompt_is_versioned_and_contains_os_identity():
    prompt = build_prompt(mode="aura", language="tr", memories=["Kullanıcı kitap yazmak istiyor."])
    assert AURA_PROMPT_VERSION == "aura_persona_v1"
    assert "AURA" in prompt
    assert "SANRI OS" in prompt
    assert "Kullanıcı kitap yazmak istiyor." in prompt
    assert "We never started from zero." in prompt
    assert "Recall who this person is" in prompt


def test_character_bible_is_present():
    bible = Path(__file__).parents[1] / "docs" / "aura-character-bible-v1.md"
    text = bible.read_text(encoding="utf-8")
    assert "AURA CHARACTER BIBLE v1.0" in text
    assert "İnsan, her zaman, yapay zekâdan daha değerlidir." in text


def test_rate_limiter_allows_different_users():
    enforce_rate_limit(str(uuid4()), 1)


def test_aura_reports_are_removed_from_user_visible_text():
    text, state, progress = extract_aura_reports(
        'Hazırım.\n<AURA_STATE_UPDATE>{"active_project":"Memory Engine"}</AURA_STATE_UPDATE>'
        '<TODAY_PROGRESS>{"items":["Sonraki adım hazırlandı"]}</TODAY_PROGRESS>'
    )
    assert text == "Hazırım."
    assert state == {"active_project": "Memory Engine"}
    assert progress == {"items": ["Sonraki adım hazırlandı"]}


def test_consciousness_layer_keeps_session_context_explicit():
    context = ConsciousnessContext("build", "deep_work", "Memory Engine'i tamamlamak", "focused")
    block = context.prompt_block()
    assert "Intent: build" in block
    assert "Session Goal: Memory Engine'i tamamlamak" in block


def test_reflection_after_action_is_private_metadata():
    text, reflection = extract_reflection_after_action(
        'Devam edelim.\n<REFLECTION_AFTER_ACTION>{"what_changed_today":"Persona tamamlandı","what_should_i_remember":"AURA persona v1","next_smallest_step":"Memory Engine"}</REFLECTION_AFTER_ACTION>'
    )
    assert text == "Devam edelim."
    assert reflection["next_smallest_step"] == "Memory Engine"


def test_create_mode_is_output_first():
    instruction = build_consciousness_instruction(
        ConsciousnessContext("create", "deep_work", "Reel serisi", "curious")
    )
    assert "3-5" in instruction
    assert "üretim paketine" in instruction
    assert "uzun felsefi" in instruction


def test_intent_router_prioritizes_explicit_production_requests():
    message = "Bana 10 güçlü Reel fikri ver."
    assert detect_production_intent(message) == "reel_topics"
    router = build_intent_router_instruction(message)
    assert "5-10" in router
    assert "En güçlü seçeneği" in router
    assert "tam senaryoya" in router


def test_intent_router_allows_explicit_reflection():
    assert detect_production_intent("Birlikte düşünelim, bunu anlamak istiyorum.") is None


def test_intent_router_detects_planning_and_building_language():
    message = "Markamı anlatan bir sistem kurmak istiyorum, planlamada nasıl yardımcı olabilirsin?"
    assert detect_production_intent(message) == "plans"


def test_intent_router_detects_book_creation():
    message = "Aşk hakkında kitap yazmak istiyorum."
    assert detect_production_intent(message) == "book_creation"
    router = build_intent_router_instruction(message)
    assert "bölüm omurgası" in router
