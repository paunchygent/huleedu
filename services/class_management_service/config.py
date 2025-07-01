from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Class Management Service.

    These settings can be overridden via environment variables prefixed with
    CLASS_MANAGEMENT_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    SERVICE_NAME: str = "class_management_service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    REDIS_URL: str = "redis://redis:6379"
    DB_USER: str = "user"
    DB_PASSWORD: str = "password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "huledu_class_management"
    DATABASE_URL: str | None = None

    @model_validator(mode="before")
    def assemble_db_connection(cls, v: Any) -> Any:
        if isinstance(v, dict) and v.get("DATABASE_URL") is None:
            v["DATABASE_URL"] = (
                f"postgresql+asyncpg://{v.get('DB_USER')}:{v.get('DB_PASSWORD')}"
                f"@{v.get('DB_HOST')}:{v.get('DB_PORT')}/{v.get('DB_NAME')}"
            )
        return v

    PORT: int = 5002
    HOST: str = "0.0.0.0"
    USE_MOCK_REPOSITORY: bool = False

    # Circuit Breaker Configuration
    CIRCUIT_BREAKER_ENABLED: bool = Field(
        default=True,
        description="Enable circuit breaker protection for external service calls"
    )

    # Kafka Circuit Breaker Configuration
    KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=10,
        description="Number of failures before opening circuit for Kafka publishing"
    )
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=30,
        description="Seconds to wait before attempting recovery for Kafka"
    )
    KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=3,
        description="Successful calls needed to close circuit for Kafka"
    )
    KAFKA_FALLBACK_QUEUE_SIZE: int = Field(
        default=1000,
        description="Maximum size of fallback queue for failed Kafka messages"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CLASS_MANAGEMENT_SERVICE_",
    )


settings = Settings()
