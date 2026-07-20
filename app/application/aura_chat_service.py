"""The single application entry point for AURA chat orchestration."""

from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.services.ai_provider import AIProvider, ProviderUsage
from app.services.aura_engine import AuraEngine
from app.services.consciousness_layer import ConsciousnessContext
from app.services.intent_router import IntentRoute, route_message


class AuraChatService:
    """Coordinates AURA context construction and provider streaming.

    API routes own transport and persistence. This service owns the application
    use case so legacy adapters and future clients can converge on one path.
    """

    def __init__(self, *, engine: AuraEngine | None = None):
        self.engine = engine or AuraEngine()

    @property
    def memory_retrieval_count(self) -> int:
        return self.engine.last_retrieval_count

    def resolve_route(
        self,
        message: str,
        *,
        requested_mode: str | None = None,
        active_project_id: str | None = None,
    ) -> IntentRoute:
        return route_message(
            message,
            requested_mode=requested_mode,
            active_project_id=active_project_id,
        )

    def build_system_prompt(
        self,
        db: Session,
        *,
        user_id: str,
        mode: str,
        language: str,
        memory_consent: bool,
        user_message: str,
        active_project_id: str | None,
        consciousness: ConsciousnessContext | None,
    ) -> str:
        return self.engine.build_system_prompt(
            db,
            user_id=user_id,
            mode=mode,
            language=language,
            memory_consent=memory_consent,
            user_message=user_message,
            active_project_id=active_project_id,
            consciousness=consciousness,
        )

    async def stream(
        self,
        provider: AIProvider,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[tuple[str, ProviderUsage | None]]:
        async for delta, usage in provider.stream(system=system, messages=messages):
            yield delta, usage
