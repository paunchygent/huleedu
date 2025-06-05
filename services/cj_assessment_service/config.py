"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderSettings(BaseModel):
    """Configuration settings for a specific LLM provider."""

    api_base: str
    default_model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    api_key_env_var: str  # Environment variable name for API key


class Settings(BaseSettings):
    """Configuration settings for the CJ Assessment Service."""

    # Basic service configuration
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "cj_assessment_service"

    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    CONSUMER_GROUP_ID_CJ: str = "cj_assessment_consumer_group"
    PRODUCER_CLIENT_ID_CJ: str = "cj_assessment_producer"

    # Kafka topic names
    CJ_ASSESSMENT_REQUEST_TOPIC: str = "huleedu.els.cj_assessment.requested.v1"
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = "huleedu.cj_assessment.completed.v1"
    CJ_ASSESSMENT_FAILED_TOPIC: str = "huleedu.cj_assessment.failed.v1"

    # External service URLs
    CONTENT_SERVICE_URL: str = "http://localhost:8002"

    # Database configuration
    DATABASE_URL_CJ: str = "sqlite+aiosqlite:///./cj_assessment.db"

    # Database Connection Pool Settings (following BOS/ELS pattern)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    # Legacy LLM provider API keys (maintained for backward compatibility)
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    # Default LLM provider and model
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

    # Structured LLM provider configuration
    LLM_PROVIDERS_CONFIG: Dict[str, LLMProviderSettings] = {
        "openai": LLMProviderSettings(
            api_base="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="OPENAI_API_KEY",
        ),
        "anthropic": LLMProviderSettings(
            api_base="https://api.anthropic.com/v1",
            default_model="claude-3-haiku-20240307",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        "google": LLMProviderSettings(
            api_base="https://generativelanguage.googleapis.com/v1",
            default_model="gemini-1.5-flash",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="GOOGLE_API_KEY",
        ),
        "openrouter": LLMProviderSettings(
            api_base="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-3-haiku",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="OPENROUTER_API_KEY",
        ),
    }

    # Global LLM configuration defaults (used as fallbacks)
    LLM_REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_TOKENS_RESPONSE: int = 1000
    TEMPERATURE: float = 0.1

    # CJ assessment parameters
    MAX_PAIRWISE_COMPARISONS: int = 1000
    COMPARISONS_PER_STABILITY_CHECK_ITERATION: int = 10
    SCORE_STABILITY_THRESHOLD: float = 0.05

    # Assessment prompt template
    ASSESSMENT_PROMPT_TEMPLATE: str = """
Compare these two essays and determine which is better written.
Essay A (ID: {essay_a_id}):
{essay_a_text}

Essay B (ID: {essay_b_id}):
{essay_b_text}

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)
Based on clarity, structure, argument quality, and writing mechanics.
Always respond with valid JSON.
"""

    # System prompt for LLM
    SYSTEM_PROMPT: str = """
You are an expert essay evaluator. Compare essays based on clarity, structure,
argument quality, and writing mechanics. Always respond with valid JSON.
"""

    # Metrics configuration
    METRICS_PORT: int = 9090

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CJ_ASSESSMENT_SERVICE_",
    )


settings = Settings()
