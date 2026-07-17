import pytest

from app.services.intent_router import route_message
from app.services.prompt_assets import mode_prompt


@pytest.mark.parametrize(
    "message",
    [
        "Bu kararı nasıl değerlendirmeliyim?",
        "İki seçenek arasında kaldım.",
        "Bu konuda ne düşünüyorsun?",
        "Neden böyle hissettiğimi anlamak istiyorum.",
        "Bir karar vermeden önce birlikte bakalım.",
        "Bu fikrin çelişkisi nerede?",
        "Bunu daha net görmek istiyorum.",
        "Bana farklı açılardan bakar mısın?",
        "Bu konuşmayı berraklaştırmak istiyorum.",
        "Birlikte düşünelim.",
    ],
)
def test_think_mode_routes_to_reflection(message):
    route = route_message(message, requested_mode="think")
    assert route.requested_mode == "think"
    assert route.expected_output_type == "reflection"


@pytest.mark.parametrize(
    "message",
    [
        "Bir reel fikri ver.",
        "Bana içerik üret.",
        "Bir kitap başlığı bul.",
        "Senaryo yaz.",
        "Kampanya fikri oluştur.",
        "Bir proje adı öner.",
        "10 fikir listele.",
        "Bir podcast konsepti bul.",
        "Kitap yazmak istiyorum.",
        "Bir sunum planı hazırla.",
    ],
)
def test_create_intent_routes_to_usable_output(message):
    route = route_message(message, requested_mode="create")
    assert route.requested_mode == "create"
    assert route.expected_output_type in {"idea_list", "production_package", "script_or_outline"}
    assert route.needs_clarification is False


@pytest.mark.parametrize("message", ["Devam edelim."] * 10)
def test_project_mode_keeps_next_step_visible(message):
    route = route_message(message, requested_mode="projects", active_project_id="project-1")
    assert route.requested_mode == "projects"
    assert route.detected_intent == "continue_project"
    assert route.expected_output_type == "project_plan"
    assert route.memory_context_required is True


@pytest.mark.parametrize(
    "message",
    [
        "Rüyamı anlatmak istiyorum.",
        "Bu sembol ne hissettiriyor?",
        "Günlüğüme yazmak istiyorum.",
        "Dün gece su gördüm.",
        "Bir çağrışımın peşinden gitmek istiyorum.",
        "Rüyadaki ev aklımda kaldı.",
        "İç dünyama dönmek istiyorum.",
        "Bu görüntünün bende anlamı ne?",
        "Bir sembol üzerine bakalım.",
        "Hatırladığım duyguyu anlamak istiyorum.",
    ],
)
def test_explore_mode_routes_to_uncertain_exploration(message):
    route = route_message(message, requested_mode="explore")
    assert route.requested_mode == "explore"
    assert route.detected_intent == "explore_dream"
    assert route.expected_output_type == "exploration"
    assert route.needs_clarification is True


@pytest.mark.parametrize("mode", ["think", "create", "projects", "explore"])
def test_mode_prompt_assets_exist(mode):
    prompt = mode_prompt(mode)
    assert f"ACTIVE MODE: {mode}" in prompt
    assert "SUCCESS:" in prompt
