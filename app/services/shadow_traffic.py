"""Safe shadow-traffic primitives.

Sprint 3.1 records routing parity without issuing a second model request.
Full response shadowing requires an approved executor, identity mapping, and
cost/privacy limits; it is deliberately not enabled by default.
"""

from app.core.logging import log_migration_metric


def record_shadow_routing(
    *,
    same_mode: bool,
    same_intent: bool,
    same_output_type: bool,
) -> None:
    log_migration_metric(
        "shadow_routing_comparison",
        route="migration",
        shadow=True,
        status=(
            "match"
            if same_mode and same_intent and same_output_type
            else "difference"
        ),
    )
