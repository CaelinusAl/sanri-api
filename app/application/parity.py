"""Content-free parity and shadow observations for migration cohorts."""

from dataclasses import asdict

from app.services.intent_router import route_message


def compare_routing(message: str, requested_mode: str | None = None) -> dict[str, object]:
    """Compare the shared legacy/V1 routing contract without model calls."""
    legacy = route_message(message, requested_mode=requested_mode)
    v1 = route_message(message, requested_mode=requested_mode)
    legacy_data = asdict(legacy)
    v1_data = asdict(v1)
    return {
        "same_mode": legacy_data["requested_mode"] == v1_data["requested_mode"],
        "same_intent": legacy_data["detected_intent"] == v1_data["detected_intent"],
        "same_output_type": legacy_data["expected_output_type"] == v1_data["expected_output_type"],
        "legacy": legacy_data,
        "v1": v1_data,
    }
