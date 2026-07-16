from sqlalchemy.orm import Session

from app.services.memory_service import memory_context
from app.services.prompt_builder import AURA_PROMPT_VERSION, build_prompt
from app.services.aura_state_service import state_context
from app.services.consciousness_layer import ConsciousnessContext, build_consciousness_instruction


class AuraEngine:
    """Builds the versioned AURA context without knowing the model provider."""

    prompt_version = AURA_PROMPT_VERSION

    def build_system_prompt(
        self,
        db: Session,
        *,
        user_id: str,
        mode: str,
        language: str,
        memory_consent: bool,
        consciousness: ConsciousnessContext | None = None,
        user_message: str = "",
    ) -> str:
        memories = memory_context(db, user_id) if memory_consent else []
        prompt = build_prompt(mode=mode, language=language, memories=memories)
        if consciousness:
            prompt += "\n\n" + build_consciousness_instruction(consciousness, user_message)
        return prompt + "\n\nAURA STATE:\n" + state_context(db, user_id)
