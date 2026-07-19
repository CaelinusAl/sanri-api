"""Transport-only adapter for the legacy bilinc-alani contract.

The adapter intentionally contains no prompt, memory, intent, or provider
rules. Those rules remain in the application/domain path and can be migrated
without changing the old request/response shape.
"""

from collections.abc import Callable
import os
from typing import Any

from app.core.logging import log_migration_metric
from app.application.parity import compare_routing
from app.services.shadow_traffic import record_shadow_routing


class LegacyCompatibilityAdapter:
    def __init__(self, legacy_handler: Callable[..., dict[str, Any]]):
        self._legacy_handler = legacy_handler

    def handle(self, **payload: Any) -> dict[str, Any]:
        try:
            if os.getenv("SHADOW_TRAFFIC_ENABLED", "false").casefold() in {"1", "true", "yes"}:
                message = str(payload.get("user_message") or payload.get("message") or "")
                mode = payload.get("requested_mode")
                if message:
                    comparison = compare_routing(message, mode)
                    record_shadow_routing(
                        same_mode=bool(comparison["same_mode"]),
                        same_intent=bool(comparison["same_intent"]),
                        same_output_type=bool(comparison["same_output_type"]),
                    )
            result = self._legacy_handler(**payload)
            log_migration_metric("legacy_fallback", route="legacy", status="success", fallback=True)
            return result
        except Exception:
            log_migration_metric("legacy_fallback", route="legacy", status="error", fallback=True)
            raise
