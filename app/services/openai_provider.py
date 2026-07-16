from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import Settings
from app.services.ai_provider import ProviderUsage


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.settings = settings
        self.model = settings.openai_model
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def stream(self, *, system: str, messages: list[dict[str, str]]) -> AsyncIterator[tuple[str, ProviderUsage | None]]:
        response = await self.client.responses.create(
            model=self.model,
            instructions=system,
            input=messages,
            stream=True,
        )
        async for event in response:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                yield getattr(event, "delta", ""), None
            elif event_type == "response.completed":
                usage = getattr(getattr(event, "response", None), "usage", None)
                yield "", ProviderUsage(
                    input_tokens=getattr(usage, "input_tokens", 0) or 0,
                    output_tokens=getattr(usage, "output_tokens", 0) or 0,
                    estimated_cost_usd=(
                        ((getattr(usage, "input_tokens", 0) or 0) / 1_000_000) * self.settings.openai_input_cost_per_1m_usd
                        + ((getattr(usage, "output_tokens", 0) or 0) / 1_000_000) * self.settings.openai_output_cost_per_1m_usd
                    ),
                )
