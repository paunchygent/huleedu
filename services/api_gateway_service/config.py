"""
Configuration for API Gateway Service.

Uses Pydantic settings for environment-based configuration with
FastAPI-specific settings and Svelte 5 + Vite frontend integration.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

from common_core.config_enums import Environment
from huleedu_service_libs.auth import JWTValidationSettings
from huleedu_service_libs.config import SecureServiceSettings


class Settings(SecureServiceSettings, JWTValidationSettings):
    """Configuration settings for API Gateway Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="API_GATEWAY_",
        case_sensitive=False,
        extra="ignore",  # Allow extra environment variables to be ignored
    )

    # Service identity
    SERVICE_NAME: str = "api-gateway-service"

    # ENVIRONMENT inherited from SecureServiceSettings with validation_alias
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )

    # HTTP server configuration
    HTTP_HOST: str = Field(default="0.0.0.0", description="HTTP server host")
    HTTP_PORT: int = Field(default=4001, description="HTTP server port")

    # Logging configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # CORS configuration for Svelte 5 + Vite frontend
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
        description="Allowed CORS origins for Svelte 5 + Vite frontend",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True, description="Allow credentials in CORS requests"
    )
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS",
    )
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"], description="Allowed headers for CORS requests"
    )

    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka:9092", description="Kafka bootstrap servers"
    )

    # Security
    # JWT validation settings inherited from JWTValidationSettings
    # Only override defaults here if needed for API Gateway specifically
    JWT_ORG_ID_CLAIM_NAMES: list[str] = Field(
        default_factory=lambda: ["org_id", "org", "organization_id"],
        description=(
            "Ordered list of JWT claim names to check for organization identity. "
            "First matching non-empty string value is used as org_id."
        ),
    )

    # HTTP Client Timeouts
    HTTP_CLIENT_TIMEOUT_SECONDS: int = 30
    HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS: int = 10

    # Service URLs & Strategies
    CMS_API_URL: str = Field(
        default="http://class_management_service:8000",
        description="Class Management Service base URL",
        validation_alias=AliasChoices("API_GATEWAY_CMS_API_URL", "CLASS_MANAGEMENT_SERVICE_URL"),
    )
    FILE_SERVICE_URL: str = Field(
        default="http://file_service:8000",
        description="File Service base URL for file upload proxy",
        validation_alias=AliasChoices("API_GATEWAY_FILE_SERVICE_URL", "FILE_SERVICE_URL"),
    )
    RESULT_AGGREGATOR_URL: str = Field(
        default="http://result_aggregator_service:8000",
        description="Result Aggregator Service base URL",
        validation_alias=AliasChoices(
            "API_GATEWAY_RESULT_AGGREGATOR_URL", "RESULT_AGGREGATOR_SERVICE_URL"
        ),
    )
    BOS_URL: str = Field(
        default="http://batch_orchestrator_service:5000",
        description="Batch Orchestrator Service internal base URL",
        validation_alias=AliasChoices("API_GATEWAY_BOS_URL", "BATCH_ORCHESTRATOR_SERVICE_URL"),
    )

    # Redis configuration
    REDIS_URL: str = Field(
        default="redis://redis:6379",
        description="Redis URL for rate limiting and pub/sub",
    )

    # Rate limiting configuration
    RATE_LIMIT_REQUESTS: int = Field(
        default=100, description="Rate limit: requests per minute per client"
    )
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")

    # Environment type (removed - using ENVIRONMENT enum from SecureServiceSettings)

    # Circuit breaker configuration
    CIRCUIT_BREAKER_ENABLED: bool = Field(
        default=True, description="Enable circuit breaker protection for HTTP clients"
    )
    HTTP_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5, description="Circuit breaker failure threshold"
    )
    HTTP_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=60, description="Circuit breaker recovery timeout in seconds"
    )
    HTTP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=2, description="Circuit breaker success threshold for half-open state"
    )


# Global settings instance
settings = Settings()
