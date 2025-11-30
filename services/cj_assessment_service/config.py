"""Configuration settings for the CJ Assessment Service."""

from __future__ import annotations

from common_core import Environment, LLMBatchingMode, LLMProviderType
from common_core.event_enums import ProcessingEvent, topic_name
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.auth import JWTValidationSettings
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings, JWTValidationSettings):
    """Configuration settings for the CJ Assessment Service."""

    # Basic service configuration
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "cj_assessment_service"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )
    VERSION: str = "1.0.0"
    ENABLE_ADMIN_ENDPOINTS: bool = Field(
        default=True,
        description=(
            "Enable /admin/v1 routes. Forced to False in production unless explicitly set."
        ),
    )

    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers for event consumption and publishing",
    )
    CONSUMER_GROUP_ID_CJ: str = "cj_assessment_consumer_group"
    PRODUCER_CLIENT_ID_CJ: str = "cj_assessment_producer"

    # Redis configuration for idempotency
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for idempotency and caching"
    )

    # Kafka topic names
    CJ_ASSESSMENT_REQUEST_TOPIC: str = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    CJ_ASSESSMENT_FAILED_TOPIC: str = topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)
    ASSESSMENT_RESULT_TOPIC: str = Field(
        default="huleedu.assessment.result.published.v1",
        description="Topic for publishing assessment results to RAS",
    )

    # External service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"

    # Database configuration - PostgreSQL only (no sqlite fallback)
    DB_HOST: str = Field(
        default="localhost",
        description="PostgreSQL host when running outside Docker",
    )
    DB_PORT: int = Field(
        default=5434,
        description="PostgreSQL port when running outside Docker (mapped from container)",
    )
    DB_NAME: str = Field(
        default="huleedu_cj_assessment",
        description="Primary database name for CJ Assessment",
    )
    DB_USER: str = Field(
        default="huleedu_user",
        description="Database user name (falls back to HULEEDU_DB_USER env)",
    )

    # Database Connection Pool Settings (following BOS/ELS pattern)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Uses shared database URL helper to construct environment-aware connection strings.
        Automatically handles password encoding and production/development environments.
        """
        import os

        # Determine host and port based on ENV_TYPE
        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("CJ_ASSESSMENT_SERVICE_DB_HOST", "cj_assessment_db")
            dev_port_str = os.getenv("CJ_ASSESSMENT_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5434"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_cj_assessment",
            service_env_var_prefix="CJ_ASSESSMENT_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    # Default LLM provider for centralized service requests
    DEFAULT_LLM_PROVIDER: LLMProviderType = LLMProviderType.OPENAI
    DEFAULT_LLM_MODEL: str = Field(
        default="gpt-5-mini-2025-08-07",
        description="Default LLM model to use for comparison requests",
    )
    LLM_BATCHING_MODE: LLMBatchingMode = Field(
        default=LLMBatchingMode.SERIAL_BUNDLE,
        description=(
            "How CJ submits comparisons to LLM Provider: per_request, serial_bundle, "
            "provider_batch_api."
        ),
    )
    LLM_BATCH_API_ALLOWED_PROVIDERS: list[LLMProviderType] = Field(
        default_factory=lambda: [LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC],
        description=(
            "Providers eligible for PROVIDER_BATCH_API mode. If a batch selects "
            "provider_batch_api but the resolved provider is not listed here, CJ "
            "automatically falls back to the next safest batching mode."
        ),
    )
    ENABLE_LLM_BATCHING_METADATA_HINTS: bool = Field(
        default=False,
        description=(
            "When true, CJLLMComparisonMetadata emits batching hints such as "
            "cj_llm_batching_mode and comparison_iteration into request_metadata."
        ),
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
    MAX_PAIRWISE_COMPARISONS: int = 300

    # NOTE:
    # These BT convergence parameters are already used in pure math
    # helpers (e.g. scoring_ranking.check_score_stability) and in the
    # callback-driven continuation loop to decide when scores are
    # stable enough to stop requesting more comparisons.
    MIN_COMPARISONS_FOR_STABILITY_CHECK: int = Field(
        default=12,
        description="Minimum successful comparisons required before checking score stability",
    )
    SCORE_STABILITY_THRESHOLD: float = 0.05

    # BT SE diagnostics (observability-only; no gating semantics)
    BT_MEAN_SE_WARN_THRESHOLD: float = Field(
        default=0.4,
        description=(
            "Diagnostic threshold for batch-level mean BT standard error. "
            "Used only for BT SE inflated batch quality indicators."
        ),
    )
    BT_MAX_SE_WARN_THRESHOLD: float = Field(
        default=0.8,
        description=(
            "Diagnostic threshold for maximum BT standard error across essays. "
            "Used only for BT SE inflated batch quality indicators."
        ),
    )
    BT_MIN_MEAN_COMPARISONS_PER_ITEM: float = Field(
        default=1.0,
        description=(
            "Minimum mean comparisons per essay before marking comparison coverage as sparse. "
            "Used only for comparison coverage sparse batch quality indicators."
        ),
    )

    # Small-net Phase-2 resampling controls (PR-7)
    MIN_RESAMPLING_NET_SIZE: int = Field(
        default=10,
        description=(
            "Nets with expected_essay_count below this threshold are treated as small and "
            "eligible for limited Phase-2 resampling semantics."
        ),
    )
    MAX_RESAMPLING_PASSES_FOR_SMALL_NET: int = Field(
        default=2,
        description=(
            "Maximum number of Phase-2 resampling passes allowed for small nets once "
            "unique pairwise coverage is complete."
        ),
    )

    # Pair generation configuration
    PAIR_GENERATION_SEED: int | None = Field(
        default=None,
        description=(
            "Optional seed for deterministic pair position randomization. "
            "Leave unset in production to preserve unbiased ordering."
        ),
    )

    # Pair matching strategy configuration (DI-swappable)
    PAIR_MATCHING_STRATEGY: str = Field(
        default="optimal_graph",
        description=(
            "Matching strategy for pair generation. "
            "Options: 'optimal_graph' (Hungarian algorithm). "
            "Future: 'random', 'd_optimal'."
        ),
    )
    MATCHING_WEIGHT_COMPARISON_COUNT: float = Field(
        default=1.0,
        description="Weight for comparison count fairness term in optimal matching.",
    )
    MATCHING_WEIGHT_BT_PROXIMITY: float = Field(
        default=0.5,
        description="Weight for BT score proximity term in optimal matching.",
    )

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

    # System prompt for LLM - CJ Assessment canonical prompt
    # This is the default for all CJ comparative judgement workflows
    # Can be overridden via llm_config_overrides.system_prompt_override in events
    SYSTEM_PROMPT: str = (
        "You are an impartial Comparative Judgement assessor for "
        "upper-secondary student essays.\n"
        "\n"
        "Constraints:\n"
        "- Maintain complete neutrality. Do not favor any topic stance, moral "
        "position, essay length, or writing style.\n"
        "- Judge strictly against the provided Student Assignment and Assessment "
        "Rubric; never invent additional criteria.\n"
        "- Return a justification of 50 words or fewer that highlights the "
        "decisive factor that made the winning essay outperform the other.\n"
        "- Report confidence as a numeric value from 0 to 5 (0 = no confidence, "
        "5 = extremely confident).\n"
        "- Respond via the comparison_result tool with fields {winner, "
        "justification, confidence}. Make sure the payload satisfies that schema "
        "exactly."
    )

    # HTTP server configuration
    HTTP_PORT: int = 9090

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
        default=9,
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

    @model_validator(mode="after")
    def _enforce_admin_toggle(self) -> "Settings":
        """Disable admin endpoints by default in production unless explicitly enabled."""

        if self.is_production() and "ENABLE_ADMIN_ENDPOINTS" not in self.model_fields_set:
            object.__setattr__(self, "ENABLE_ADMIN_ENDPOINTS", False)

        return self


settings = Settings()
