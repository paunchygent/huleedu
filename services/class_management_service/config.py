from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core.config_enums import Environment


class Settings(BaseSettings):
    """
    Configuration settings for the Class Management Service.

    These settings can be overridden via environment variables prefixed with
    CLASS_MANAGEMENT_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "class_management_service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    REDIS_URL: str = "redis://redis:6379"
    DB_USER: str = "huledu"
    DB_PASSWORD: str = "huledu_password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5435  # Class Management Service specific port
    DB_NAME: str = "huledu_class_management"

    @property
    def DATABASE_URL(self) -> str:
        """Construct the PostgreSQL database URL from configuration settings."""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    PORT: int = 5002
    HOST: str = "0.0.0.0"
    USE_MOCK_REPOSITORY: bool = False

    # Database Pool Configuration
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Maximum overflow connections")
    DATABASE_POOL_PRE_PING: bool = Field(default=True, description="Pre-ping connections")
    DATABASE_POOL_RECYCLE: int = Field(
        default=3600, description="Recycle connections after seconds"
    )

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
        env_prefix="CLASS_MANAGEMENT_SERVICE_",
    )


settings = Settings()
