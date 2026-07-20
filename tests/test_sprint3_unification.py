"""Sprint 3 Wave A — v1 chat unification core (no identity/recovery/docs deps)."""

from uuid import uuid4

from app.application.aura_chat_service import AuraChatService
from app.application.legacy_adapter import LegacyCompatibilityAdapter
from app.application.parity import compare_routing
from app.core.config import Settings
from app.services.feature_flags import rollout_bucket, v1_chat_available


def test_legacy_adapter_only_delegates_transport_payload():
    calls = {}

    def handler(**payload):
        calls.update(payload)
        return {"answer": "ok"}

    result = LegacyCompatibilityAdapter(handler).handle(message="hello", session_id="s1")

    assert result == {"answer": "ok"}
    assert calls == {"message": "hello", "session_id": "s1"}


def test_aura_chat_service_delegates_prompt_to_aura_engine():
    class FakeEngine:
        def build_system_prompt(self, db, **kwargs):
            assert kwargs["user_message"] == "hello"
            return "AURA SYSTEM"

    service = AuraChatService(engine=FakeEngine())

    assert (
        service.build_system_prompt(
            object(),
            user_id=str(uuid4()),
            mode="aura",
            language="tr",
            memory_consent=False,
            user_message="hello",
            active_project_id=None,
            consciousness=None,
        )
        == "AURA SYSTEM"
    )


def test_rollout_is_deterministic_and_percentage_bounded():
    settings = Settings(v1_chat_enabled=True, v1_chat_percentage=100)
    assert rollout_bucket("user-1") == rollout_bucket("user-1")
    assert v1_chat_available(settings, "user-1") is True
    assert v1_chat_available(settings.model_copy(update={"v1_chat_percentage": 0}), "user-1") is False


def test_legacy_and_v1_route_through_the_same_intent_router():
    service = AuraChatService()
    legacy_route = service.resolve_route("Bir reel fikri üret.", requested_mode="create")
    v1_route = service.resolve_route("Bir reel fikri üret.", requested_mode="create")

    assert legacy_route == v1_route
    assert legacy_route.expected_output_type == "idea_list"


def test_routing_shadow_observation_is_content_free_and_parity_safe():
    comparison = compare_routing("Bir reel fikri üret.", "create")

    assert comparison["same_mode"] is True
    assert comparison["same_intent"] is True
    assert comparison["same_output_type"] is True
