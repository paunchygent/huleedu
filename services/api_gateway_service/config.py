"""
Configuration for API Gateway Service.

Uses Pydantic settings for environment-based configuration with
FastAPI-specific settings and React frontend integration.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for API Gateway Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="API_GATEWAY_",
        case_sensitive=False,
        extra="ignore"  # Allow extra environment variables to be ignored
    )

    # Service identity
    SERVICE_NAME: str = "api-gateway-service"

    # HTTP server configuration
    HTTP_HOST: str = Field(default="0.0.0.0", description="HTTP server host")
    HTTP_PORT: int = Field(default=4001, description="HTTP server port")

    # Logging configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # CORS configuration for React frontend
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        description="Allowed CORS origins for React frontend",
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
    JWT_SECRET_KEY: str = "a-very-secret-key-that-must-be-in-secrets-manager"
    JWT_ALGORITHM: str = "HS256"

    # HTTP Client Timeouts
    HTTP_CLIENT_TIMEOUT_SECONDS: int = 30
    HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS: int = 10

    # Service URLs & Strategies
    CMS_API_URL: str = Field(
        default="http://class_management_service:8000",
        description="Class Management Service base URL",
    )
    FILE_SERVICE_URL: str = Field(
        default="http://file_service:8000",
        description="File Service base URL for file upload proxy",
    )
    RESULT_AGGREGATOR_URL: str = Field(
        default="http://result_aggregator_service:8000",
        description="Result Aggregator Service base URL",
    )
    BOS_URL: str = Field(
        default="http://batch_orchestrator_service:8000",
        description="Batch Orchestrator Service base URL for fallback queries",
    )
    HANDLE_MISSING_BATCHES: str = Field(
        default="query_bos",
        description="Strategy for 404 batches: 'query_bos' or 'return_404'",
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

    # Environment type
    ENV_TYPE: str = Field(default="development", description="Environment type")


# Global settings instance
settings = Settings()
