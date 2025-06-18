"""
Configuration for Batch Conductor Service.

Uses Pydantic settings for environment-based configuration.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Batch Conductor Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BCS_",
        case_sensitive=False,
        extra="ignore",  # Allow extra environment variables
    )

    # Service identity
    SERVICE_NAME: str = "batch-conductor-service"

    # Pipeline configuration
    PIPELINE_CONFIG_PATH: str = "services/batch_conductor_service/pipelines.yaml"

    # HTTP server configuration
    HTTP_HOST: str = Field(default="0.0.0.0", description="HTTP server host")
    HTTP_PORT: int = Field(default=4002, description="HTTP server port")

    # Logging configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Essay Lifecycle Service integration
    ESSAY_LIFECYCLE_SERVICE_URL: str = Field(
        default="http://essay_lifecycle_service:6001",
        description="Base URL for Essay Lifecycle Service API",
    )

    # HTTP client configuration
    HTTP_TIMEOUT: int = Field(default=30, description="HTTP client timeout in seconds")
    HTTP_MAX_RETRIES: int = Field(default=3, description="Maximum HTTP client retries")

    # Environment type
    ENV_TYPE: str = Field(default="development", description="Environment type")

    # Event-driven architecture configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for event consumption"
    )

    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for state caching and idempotency"
    )

    REDIS_TTL_SECONDS: int = Field(
        default=604800,  # 7 days
        description="Redis TTL for essay state data in seconds",
    )

    # Kafka consumer configuration
    KAFKA_CONSUMER_GROUP_ID: str = Field(
        default="bcs-event-consumer", description="Kafka consumer group ID"
    )

    KAFKA_AUTO_OFFSET_RESET: str = Field(
        default="latest", description="Kafka auto offset reset policy"
    )


# Global settings instance
settings = Settings()
