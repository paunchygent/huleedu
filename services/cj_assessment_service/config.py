"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core import LLMProviderType


class Settings(BaseSettings):
    """Configuration settings for the CJ Assessment Service."""

    # Basic service configuration
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "cj_assessment_service"

    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONSUMER_GROUP_ID_CJ: str = "cj_assessment_consumer_group"
    PRODUCER_CLIENT_ID_CJ: str = "cj_assessment_producer"

    # Redis configuration for idempotency
    REDIS_URL: str = "redis://localhost:6379"

    # Kafka topic names
    CJ_ASSESSMENT_REQUEST_TOPIC: str = "huleedu.els.cj_assessment.requested.v1"
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = "huleedu.cj_assessment.completed.v1"
    CJ_ASSESSMENT_FAILED_TOPIC: str = "huleedu.cj_assessment.failed.v1"

    # External service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"

    # Database configuration - PostgreSQL only (no sqlite fallback)
    # DATABASE_URL_CJ removed - use database_url property for consistent PostgreSQL access

    # Database Connection Pool Settings (following BOS/ELS pattern)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Standardized PostgreSQL configuration following HuleEduApp pattern.
        Uses environment-specific connection details.
        """
        import os

        # Check for environment variable first (Docker environment)
        env_url = os.getenv("CJ_ASSESSMENT_SERVICE_DATABASE_URL_CJ")
        if env_url:
            return env_url

        # Fallback to local development configuration
        db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
        db_password = os.getenv("HULEEDU_DB_PASSWORD", "ted5?SUCwef3-JIVres6!DEK")
        return f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5434/cj_assessment"

    # Default LLM provider for centralized service requests
    DEFAULT_LLM_PROVIDER: LLMProviderType = LLMProviderType.OPENAI
    DEFAULT_LLM_MODEL: str = Field(
        default="gpt-4.1",
        description="Default LLM model to use for comparison requests",
    )

    # LLM Provider Service configuration
    LLM_PROVIDER_SERVICE_URL: str = Field(
        default="http://llm_provider_service:8080/api/v1",
        description="Base URL for centralized LLM Provider Service",
    )

    # LLM callback configuration
    LLM_PROVIDER_CALLBACK_TOPIC: str = Field(
        default="huleedu.llm_provider.comparison_result.v1",
        description="Kafka topic for LLM comparison callbacks",
    )

    # Batch processing configuration
    BATCH_TIMEOUT_HOURS: int = Field(
        default=4, description="Hours before considering a batch stuck"
    )
    BATCH_MONITOR_INTERVAL_MINUTES: int = Field(
        default=5, description="Interval for batch health checks"
    )
    MIN_SUCCESS_RATE_THRESHOLD: float = Field(
        default=0.8, description="Minimum success rate before failing batch"
    )

    # Score stability configuration
    MAX_ITERATIONS: int = Field(default=5, description="Maximum comparison iterations")

    # Performance tuning
    MAX_CONCURRENT_COMPARISONS: int = Field(
        default=100, description="Max comparisons per batch in flight"
    )

    # Global LLM configuration defaults (used as fallbacks)
    LLM_REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_TOKENS_RESPONSE: int = 1000
    TEMPERATURE: float = 0.1
    DEFAULT_LLM_TEMPERATURE: float = 0.1  # Add this for compatibility

    # Retry configuration for LLM requests
    llm_retry_enabled: bool = True
    llm_retry_attempts: int = 3  # Changed from llm_retry_max_attempts
    llm_retry_wait_min_seconds: float = 1.0  # Changed from llm_retry_base_delay_seconds
    llm_retry_wait_max_seconds: float = 30.0  # Changed from llm_retry_max_delay_seconds
    llm_retry_exponential_base: float = 2.0
    llm_retry_on_exception_names: list[str] = []  # Empty list uses defaults

    # CJ assessment parameters
    MAX_PAIRWISE_COMPARISONS: int = 1000
    COMPARISONS_PER_STABILITY_CHECK_ITERATION: int = 10
    SCORE_STABILITY_THRESHOLD: float = 0.05

    # Failed Comparison Pool Configuration
    FAILED_COMPARISON_RETRY_THRESHOLD: int = Field(
        default=20, description="Minimum failed comparisons needed before retry batch creation"
    )
    MAX_RETRY_ATTEMPTS: int = Field(
        default=3, description="Maximum retry attempts per failed comparison"
    )
    RETRY_BATCH_SIZE: int = Field(
        default=50, description="Size of retry batches (up to 200)"
    )
    RETRY_BATCH_PRIORITY: str = Field(
        default="high", description="Priority level for retry batches"
    )
    ENABLE_FAILED_COMPARISON_RETRY: bool = Field(
        default=True, description="Enable automatic retry of failed comparisons"
    )

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

    # Circuit Breaker Configuration
    CIRCUIT_BREAKER_ENABLED: bool = Field(
        default=True, description="Enable circuit breaker protection for external service calls"
    )

    # Kafka Circuit Breaker Configuration
    KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=10, description="Number of failures before opening circuit for Kafka publishing"
    )
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=30, description="Seconds to wait before attempting recovery for Kafka"
    )
    KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=3, description="Successful calls needed to close circuit for Kafka"
    )
    KAFKA_FALLBACK_QUEUE_SIZE: int = Field(
        default=1000, description="Maximum size of fallback queue for failed Kafka messages"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CJ_ASSESSMENT_SERVICE_",
    )


settings = Settings()
