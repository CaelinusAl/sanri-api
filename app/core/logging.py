import logging


logger = logging.getLogger("sanri.v1")


def log_ai_metrics(*, user_id: str, provider: str, model: str, latency_ms: int, input_tokens: int, output_tokens: int, estimated_cost_usd: float) -> None:
    logger.info(
        "ai_request_metrics user_id=%s provider=%s model=%s latency_ms=%s input_tokens=%s output_tokens=%s estimated_cost_usd=%.6f",
        user_id,
        provider,
        model,
        latency_ms,
        input_tokens,
        output_tokens,
        estimated_cost_usd,
    )


def log_migration_metric(event: str, **fields: object) -> None:
    """Emit allowlisted, content-free migration telemetry."""
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key
        in {
            "route",
            "mode",
            "intent",
            "status",
            "latency_ms",
            "ttft_ms",
            "provider_error",
            "streaming_interruption",
            "memory_retrieval_count",
            "session_close_success",
            "fallback",
            "shadow",
        }
    }
    logger.info("migration_metric event=%s fields=%s", event, safe_fields)
