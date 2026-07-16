from functools import lru_cache
import os

from pydantic import BaseModel, Field


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
