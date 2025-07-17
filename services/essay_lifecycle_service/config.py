"""
Configuration module for the HuleEdu Essay Lifecycle Service.

This module defines the settings and configuration for the Essay Lifecycle Service,
including Kafka connection settings, HTTP API configuration, and state persistence settings.
"""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """
    Configuration settings for the Essay Lifecycle Service.

    Settings are loaded from .env files and environment variables.
    """

    # Service Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "essay-lifecycle-service"

    # HTTP API Configuration
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000
    API_VERSION: str = "v1"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONSUMER_GROUP: str = "essay-lifecycle-service-group-v1.0"
    PRODUCER_CLIENT_ID: str = "essay-lifecycle-service-producer"
    CONSUMER_CLIENT_ID: str = "essay-lifecycle-service-consumer"

    # External Service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    BATCH_ORCHESTRATOR_SERVICE_URL: str = "http://batch_orchestrator_service:8000/v1"

    # Repository Configuration (following BOS pattern)
    USE_MOCK_REPOSITORY: bool = True  # False in production

    # SQLite Configuration (development/testing)
    DATABASE_PATH: str = "./essay_lifecycle.db"
    DATABASE_TIMEOUT: float = 30.0
    DATABASE_POOL_SIZE: int = 20

    # PostgreSQL Configuration (production)
    DATABASE_HOST: str = Field(default="essay_lifecycle_db", alias="ELS_DB_HOST")
    DATABASE_PORT: int = Field(default=5432, alias="ELS_DB_PORT")
    DATABASE_NAME: str = Field(default="essay_lifecycle", alias="ELS_DB_NAME")

    # PostgreSQL Connection Pool Settings
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"  # Development/test default

    # Observability Configuration
    PROMETHEUS_PORT: int = 9090
    ENABLE_METRICS: bool = True

    # Testing Configuration
    DISABLE_IDEMPOTENCY: bool = Field(
        default=False, description="Disable idempotency for testing purposes"
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
        env_prefix="ESSAY_LIFECYCLE_SERVICE_",
    )

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Standardized PostgreSQL configuration following HuleEdu pattern.
        Uses environment-specific connection details.
        """
        import os

        # Check for environment variable first (Docker environment)
        env_url = os.getenv("ESSAY_LIFECYCLE_SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        # Fallback to local development configuration (loaded from .env via dotenv)
        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        # For development/migration: map container names to localhost
        host = self.DATABASE_HOST
        port = self.DATABASE_PORT

        # Map container database hosts to localhost for local development
        if host == "essay_lifecycle_db":
            host = "localhost"
            port = 5433  # External port from docker-compose

        return f"postgresql+asyncpg://{db_user}:{db_password}@{host}:{port}/{self.DATABASE_NAME}"


# Create a single instance for the application to use
settings = Settings()
