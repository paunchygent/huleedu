"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from common_core import Environment, LLMProviderType
from common_core.event_enums import ProcessingEvent, topic_name
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """Configuration settings for the CJ Assessment Service."""

    # Basic service configuration
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "cj_assessment_service"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    VERSION: str = "1.0.0"

    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONSUMER_GROUP_ID_CJ: str = "cj_assessment_consumer_group"
    PRODUCER_CLIENT_ID_CJ: str = "cj_assessment_producer"

    # Redis configuration for idempotency
    REDIS_URL: str = "redis://localhost:6379"

    # Kafka topic names
    CJ_ASSESSMENT_REQUEST_TOPIC: str = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    CJ_ASSESSMENT_FAILED_TOPIC: str = topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)
    ASSESSMENT_RESULT_TOPIC: str = Field(
        default="huleedu.assessment.results.v1",
        description="Topic for publishing assessment results to RAS",
    )

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
        
        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os
        
        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("CJ_ASSESSMENT_SERVICE_DATABASE_URL_CJ") 
        if env_url:
            return env_url
            
        # Environment-based configuration
        if self.ENVIRONMENT == "production":
            # Production: External managed database
            prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
            prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
            prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD") 
            
            if not all([prod_host, prod_password]):
                raise ValueError(
                    "Production environment requires HULEEDU_PROD_DB_HOST and "
                    "HULEEDU_PROD_DB_PASSWORD environment variables"
                )
                
            return (
                f"postgresql+asyncpg://{self._db_user}:{prod_password}@"
                f"{prod_host}:{prod_port}/huleedu_cj_assessment"
            )
        else:
            # Development: Docker container (existing pattern)
            db_user = os.getenv("HULEEDU_DB_USER")
            db_password = os.getenv("HULEEDU_DB_PASSWORD") 
            
            if not db_user or not db_password:
                raise ValueError(
                    "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                    "HULEEDU_DB_PASSWORD are set in your .env file."
                )
                
            return (
                f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5434/huleedu_cj_assessment"
            )

    @property        
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os
        return os.getenv("HULEEDU_DB_USER", "huleedu_user")

    # Default LLM provider for centralized service requests
    DEFAULT_LLM_PROVIDER: LLMProviderType = LLMProviderType.OPENAI
    DEFAULT_LLM_MODEL: str = Field(
        default="gpt-5-mini-2025-08-07",
        description="Default LLM model to use for comparison requests",
    )

    # LLM Provider Service configuration
    LLM_PROVIDER_SERVICE_URL: str = Field(
        default="http://llm_provider_service:8080/api/v1",
        description="Base URL for centralized LLM Provider Service",
    )

    # LLM callback configuration
    LLM_PROVIDER_CALLBACK_TOPIC: str = Field(
        default=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        description="Kafka topic for LLM comparison callbacks",
    )

    # Batch processing configuration
    DEFAULT_BATCH_SIZE: int = Field(
        default=50, description="Default batch size for comparison processing"
    )
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
    llm_retry_on_exception_names: list[str] = [
        "asyncio.TimeoutError",
        "aiohttp.ClientError",
        "aiohttp.ClientResponseError",
    ]  # Explicit defaults for transient network/API issues

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
    RETRY_BATCH_SIZE: int = Field(default=50, description="Size of retry batches (up to 200)")
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

    # Outbox Relay Worker Configuration
    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(
        default=5.0,
        description="Maximum time to wait for Redis wake-up notification",
    )
    OUTBOX_BATCH_SIZE: int = Field(
        default=100,
        description="Maximum number of events to process per poll",
    )
    OUTBOX_MAX_RETRIES: int = Field(
        default=5,
        description="Maximum retry attempts before marking event as failed",
    )
    OUTBOX_ERROR_RETRY_INTERVAL_SECONDS: float = Field(
        default=30.0,
        description="How long to wait after an error",
    )
    OUTBOX_ENABLE_METRICS: bool = Field(
        default=True,
        description="Whether to collect Prometheus metrics for outbox",
    )
    OUTBOX_ENABLE_WAKE_NOTIFICATIONS: bool = Field(
        default=True,
        description="Whether to use Redis BLPOP for instant wake-up",
    )

    # Grade Projection Configuration (NO FEATURE FLAGS)
    MIN_ANCHORS_REQUIRED: int = Field(
        default=3,
        description="Minimum anchor essays required for projection",
    )
    MAX_HESSIAN_BATCH_SIZE: int = Field(
        default=50,
        description="Maximum essays for Hessian calculation",
    )
    CONFIDENCE_CALCULATION_TIMEOUT: int = Field(
        default=30,
        description="Timeout in seconds for confidence calculation",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CJ_ASSESSMENT_SERVICE_",
    )


settings = Settings()
