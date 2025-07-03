"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core import LLMProviderType


class LLMProviderSettings(BaseModel):
    """Configuration settings for a specific LLM provider."""

    api_base: str
    default_model: str
    temperature: float | None = None
    max_tokens: int | None = None
    api_key_env_var: str  # Environment variable name for API key


class Settings(BaseSettings):
    """Configuration settings for the CJ Assessment Service."""

    # Basic service configuration
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "cj_assessment_service"
    USE_MOCK_LLM: bool = False  # Enable mock LLM for testing (no API calls)

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
    DEFAULT_LLM_PROVIDER: LLMProviderType = LLMProviderType.OPENAI
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

    # Structured LLM provider configuration
    LLM_PROVIDERS_CONFIG: dict[LLMProviderType, LLMProviderSettings] = {
        LLMProviderType.OPENAI: LLMProviderSettings(
            api_base="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="OPENAI_API_KEY",
        ),
        LLMProviderType.ANTHROPIC: LLMProviderSettings(
            api_base="https://api.anthropic.com/v1",
            default_model="claude-3-haiku-20240307",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        LLMProviderType.GOOGLE: LLMProviderSettings(
            api_base="https://generativelanguage.googleapis.com/v1",
            default_model="gemini-1.5-flash",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="GOOGLE_API_KEY",
        ),
        LLMProviderType.OPENROUTER: LLMProviderSettings(
            api_base="https://openrouter.ai/api/v1",
            default_model="anthropic/claude-3-haiku",
            temperature=0.1,
            max_tokens=1000,
            api_key_env_var="OPENROUTER_API_KEY",
        ),
    }

    # LLM Provider Service configuration
    LLM_PROVIDER_SERVICE_URL: str = Field(
        default="http://llm_provider_service:8090/api/v1",
        description="Base URL for centralized LLM Provider Service",
    )

    # Queue-based polling configuration for LLM Provider Service
    LLM_QUEUE_POLLING_ENABLED: bool = Field(
        default=True,
        description="Enable polling for queued LLM requests (202 responses)",
    )
    LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS: float = Field(
        default=2.0,
        description="Initial delay before first queue status check in seconds",
    )
    LLM_QUEUE_POLLING_MAX_DELAY_SECONDS: float = Field(
        default=60.0,
        description="Maximum delay between queue status checks in seconds",
    )
    LLM_QUEUE_POLLING_EXPONENTIAL_BASE: float = Field(
        default=1.5,
        description="Exponential backoff base for queue polling delays",
    )
    LLM_QUEUE_POLLING_MAX_ATTEMPTS: int = Field(
        default=30,
        description="Maximum number of queue status polling attempts",
    )
    LLM_QUEUE_TOTAL_TIMEOUT_SECONDS: int = Field(
        default=900,
        description="Total timeout for queue processing in seconds (15 minutes)",
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
