from functools import lru_cache
import os

from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "SANRI OS API"
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./dev.db"))
    supabase_jwt_secret: str = Field(default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET", ""))
    supabase_jwt_audience: str = Field(default_factory=lambda: os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"))
    supabase_jwt_issuer: str = Field(default_factory=lambda: os.getenv("SUPABASE_JWT_ISSUER", ""))
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5-mini"))
    openai_input_cost_per_1m_usd: float = Field(default_factory=lambda: float(os.getenv("OPENAI_INPUT_COST_PER_1M_USD", "0")))
    openai_output_cost_per_1m_usd: float = Field(default_factory=lambda: float(os.getenv("OPENAI_OUTPUT_COST_PER_1M_USD", "0")))
    daily_token_quota: int = Field(default_factory=lambda: int(os.getenv("DAILY_TOKEN_QUOTA", "100000")))
    rate_limit_per_minute: int = Field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")))
    v1_chat_enabled: bool = Field(default_factory=lambda: _env_bool("V1_CHAT_ENABLED", True))
    v1_chat_percentage: int = Field(default_factory=lambda: int(os.getenv("V1_CHAT_PERCENTAGE", "0")), ge=0, le=100)
    legacy_chat_fallback_enabled: bool = Field(default_factory=lambda: _env_bool("LEGACY_CHAT_FALLBACK_ENABLED", True))
    legacy_memory_write_enabled: bool = Field(default_factory=lambda: _env_bool("LEGACY_MEMORY_WRITE_ENABLED", False))
    v1_session_close_enabled: bool = Field(default_factory=lambda: _env_bool("V1_SESSION_CLOSE_ENABLED", False))
    shadow_traffic_enabled: bool = Field(default_factory=lambda: _env_bool("SHADOW_TRAFFIC_ENABLED", False))
    recovery_reviewer_role: str = Field(
        default_factory=lambda: os.getenv("RECOVERY_REVIEWER_ROLE", "recovery_reviewer")
    )
    recovery_assertion_signing_secret: str = Field(
        default_factory=lambda: os.getenv("RECOVERY_ASSERTION_SIGNING_SECRET", "")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
