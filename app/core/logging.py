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
