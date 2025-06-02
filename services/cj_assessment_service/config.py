"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # LLM provider settings
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    # LLM configuration defaults
    LLM_REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_TOKENS_RESPONSE: int = 1000
    TEMPERATURE: float = 0.1

    # CJ assessment parameters
    MAX_PAIRWISE_COMPARISONS: int = 1000
    COMPARISONS_PER_STABILITY_CHECK_ITERATION: int = 10
    SCORE_STABILITY_THRESHOLD: float = 0.05

    # Assessment prompt template
    ASSESSMENT_PROMPT_TEMPLATE: str = """Compare these two essays and determine which is better written.

Essay A (ID: {essay_a_id}):
{essay_a_text}

Essay B (ID: {essay_b_id}):
{essay_b_text}

Please respond with a JSON object containing:
- "winner": "Essay A" or "Essay B"
- "justification": Brief explanation of your decision
- "confidence": Rating from 1-5 (5 = very confident)
"""

    # System prompt for LLM
    SYSTEM_PROMPT: str = """You are an expert essay evaluator. Compare essays based on clarity, structure, argument quality, and writing mechanics. Always respond with valid JSON."""

    # Metrics configuration
    METRICS_PORT: int = 9090

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CJ_ASSESSMENT_SERVICE_",
    )


settings = Settings()
