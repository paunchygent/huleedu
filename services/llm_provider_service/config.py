"""Configuration module for the HuleEdu LLM Provider Service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core import LLMProviderType


class ProviderConfig(BaseSettings):
    """Per-provider configuration with dynamic override support."""

    enabled: bool = True
    api_key: str = ""
    base_url: Optional[str] = None
    timeout: int = 300
    max_retries: int = 3
    max_concurrent_requests: int = 3

    # Rate limiting
    rate_limit_requests_per_minute: Optional[int] = None
    rate_limit_tokens_per_minute: Optional[int] = None

    # Model-specific overrides
    model_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Cost tracking
    track_costs: bool = True
    cost_per_1k_input_tokens: Optional[float] = None
    cost_per_1k_output_tokens: Optional[float] = None


class Settings(BaseSettings):
    """Configuration settings for the LLM Provider Service."""

    # Service Identity
    SERVICE_NAME: str = "llm_provider_service"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    PORT: int = 8080
    HOST: str = "0.0.0.0"

    # Testing Configuration
    USE_MOCK_LLM: bool = False  # Enable mock LLM for testing (no API calls)

    # HuleEdu Service Libs Integration
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="kafka:9092")

    # Circuit Breaker Configuration
    CIRCUIT_BREAKER_ENABLED: bool = True
    LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 120
    LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2

    # Kafka Circuit Breaker
    KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 10
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30
    KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 3
    KAFKA_FALLBACK_QUEUE_SIZE: int = 1000

    # Provider Selection Strategy
    PROVIDER_SELECTION_STRATEGY: str = Field(
        default="priority",
        description="Selection strategy: priority, round-robin, least-cost, least-latency, random",
    )
    PROVIDER_PRIORITY_ORDER: list[LLMProviderType] = Field(
        default_factory=lambda: [
            LLMProviderType.ANTHROPIC,
            LLMProviderType.OPENAI,
            LLMProviderType.GOOGLE,
            LLMProviderType.OPENROUTER,
            LLMProviderType.MOCK,
        ],
        description="Provider priority order for priority strategy",
    )

    # Provider Health Monitoring
    PROVIDER_HEALTH_CHECK_INTERVAL: int = 60  # seconds
    PROVIDER_HEALTH_CHECK_TIMEOUT: int = 10
    PROVIDER_AUTO_DISABLE_ON_ERRORS: bool = True
    PROVIDER_ERROR_THRESHOLD_FOR_DISABLE: int = 5

    # Global LLM Configuration (can be overridden per provider)
    DEFAULT_LLM_PROVIDER: LLMProviderType = LLMProviderType.ANTHROPIC
    LLM_REQUEST_TIMEOUT: int = 300
    LLM_MAX_CONCURRENT_REQUESTS: int = 3
    LLM_DEFAULT_TEMPERATURE: float = 0.7
    LLM_DEFAULT_MAX_TOKENS: int = 4096

    # Provider-specific configurations
    # These can be overridden via environment variables or API calls
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: Optional[str] = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_ENABLED: bool = True

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-4.1"
    OPENAI_ORG_ID: Optional[str] = None
    OPENAI_ENABLED: bool = True

    GOOGLE_API_KEY: str = ""
    GOOGLE_PROJECT_ID: str = ""
    GOOGLE_DEFAULT_MODEL: str = "gemini-2.5-flash"
    GOOGLE_ENABLED: bool = True

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_DEFAULT_MODEL: str = "anthropic/claude-sonnet-4"
    OPENROUTER_ENABLED: bool = True

    # Internal/Self-hosted Model Support
    INTERNAL_MODEL_ENABLED: bool = False
    INTERNAL_MODEL_BASE_URL: Optional[str] = None
    INTERNAL_MODEL_API_KEY: Optional[str] = None
    INTERNAL_MODEL_TYPE: str = Field(
        default="vllm", description="Type of internal model: vllm, ollama, custom"
    )
    INTERNAL_MODEL_NAME: Optional[str] = None
    INTERNAL_MODEL_GPU_LAYERS: int = -1

    # Queue Configuration
    QUEUE_MAX_SIZE: int = Field(
        default=1000,
        description="Maximum number of requests in queue",
    )
    QUEUE_MAX_MEMORY_MB: int = Field(
        default=100,
        description="Maximum memory usage for queue in MB",
    )
    QUEUE_HIGH_WATERMARK: float = Field(
        default=0.8,
        ge=0.5,
        le=1.0,
        description="Start rejecting requests at this usage percent",
    )
    QUEUE_LOW_WATERMARK: float = Field(
        default=0.6,
        ge=0.0,
        lt=0.8,
        description="Resume accepting requests at this usage percent",
    )
    QUEUE_REQUEST_TTL_HOURS: int = Field(
        default=4,
        description="How long requests stay in queue before expiring",
    )
    QUEUE_POLL_INTERVAL_SECONDS: float = Field(
        default=1.0,
        description="How often to check for new requests in queue",
    )
    QUEUE_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum number of retries for failed requests",
    )

    # Development Response Recording
    RECORD_LLM_RESPONSES: bool = Field(
        default=False,
        description="Record LLM responses to files for API validation (dev only)",
    )

    @field_validator("QUEUE_LOW_WATERMARK")
    @classmethod
    def validate_watermarks(cls, v: float, info: Any) -> float:
        """Ensure low watermark is less than high watermark."""
        if "QUEUE_HIGH_WATERMARK" in info.data and v >= info.data["QUEUE_HIGH_WATERMARK"]:
            raise ValueError("QUEUE_LOW_WATERMARK must be less than QUEUE_HIGH_WATERMARK")
        return v

    @field_validator("RECORD_LLM_RESPONSES")
    @classmethod
    def validate_response_recording(cls, v: bool, info: Any) -> bool:
        """Ensure response recording is only enabled in development."""
        if v and info.data.get("ENVIRONMENT", "development") != "development":
            raise ValueError("Response recording only allowed in development environment")
        return v

    # Event Publishing
    PUBLISH_LLM_USAGE_EVENTS: bool = True
    PUBLISH_DETAILED_METRICS: bool = True

    # Security & Compliance
    ENABLE_REQUEST_SANITIZATION: bool = True
    ENABLE_RESPONSE_FILTERING: bool = True
    PII_DETECTION_ENABLED: bool = False
    AUDIT_LOG_ENABLED: bool = True

    # Admin API Configuration
    ADMIN_API_ENABLED: bool = True
    ADMIN_API_KEY: Optional[str] = None
    ADMIN_ALLOWED_IPS: list[str] = Field(default_factory=list)

    # Dynamic Configuration
    ENABLE_DYNAMIC_CONFIG: bool = True
    CONFIG_REFRESH_INTERVAL: int = 60  # seconds
    CONFIG_SOURCE: str = Field(
        default="env", description="Configuration source: env, redis, postgres, api"
    )

    # Cost Management
    ENABLE_COST_TRACKING: bool = True
    COST_ALERT_THRESHOLD_USD: float = 100.0
    COST_LIMIT_USD_PER_DAY: Optional[float] = None

    # Request Routing Rules
    ROUTING_RULES_ENABLED: bool = True
    ROUTING_RULES: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Custom routing rules based on request attributes"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LLM_PROVIDER_SERVICE_",
    )

    @field_validator("PROVIDER_SELECTION_STRATEGY")
    @classmethod
    def validate_selection_strategy(cls, v: str) -> str:
        """Validate provider selection strategy."""
        valid_strategies = {"priority", "round-robin", "least-cost", "least-latency", "random"}
        if v not in valid_strategies:
            raise ValueError(f"Invalid strategy: {v}. Must be one of {valid_strategies}")
        return v

    def get_provider_config(self, provider: str) -> ProviderConfig:
        """Get configuration for a specific provider."""
        provider_upper = provider.upper()
        return ProviderConfig(
            enabled=getattr(self, f"{provider_upper}_ENABLED", True),
            api_key=getattr(self, f"{provider_upper}_API_KEY", ""),
            base_url=getattr(self, f"{provider_upper}_BASE_URL", None),
            timeout=self.LLM_REQUEST_TIMEOUT,
            max_concurrent_requests=self.LLM_MAX_CONCURRENT_REQUESTS,
        )


# Create a single instance for the application to use
settings = Settings()
