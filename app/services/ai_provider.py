from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class AIProvider(Protocol):
    name: str

    async def stream(self, *, system: str, messages: list[dict[str, str]]) -> AsyncIterator[tuple[str, ProviderUsage | None]]:
        """Yield text deltas and optionally final usage."""
