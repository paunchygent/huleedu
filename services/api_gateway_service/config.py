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
        env_file=".env", env_prefix="API_GATEWAY_", case_sensitive=False
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

    # Rate limiting configuration
    RATE_LIMIT_REQUESTS: int = Field(
        default=100, description="Rate limit: requests per minute per client"
    )
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")

    # Environment type
    ENV_TYPE: str = Field(default="development", description="Environment type")


# Global settings instance
settings = Settings()
