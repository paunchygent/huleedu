"""
Configuration module for the HuleEdu File Service.

This module defines the settings and configuration for the File Service,
including Kafka settings, Content Service URL, and service ports.
"""

from __future__ import annotations

from common_core.config_enums import Environment
from common_core.event_enums import ProcessingEvent, topic_name
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """
    Configuration settings for the File Service.

    These settings can be overridden via environment variables prefixed with
    FILE_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )
    SERVICE_NAME: str = "file-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    REDIS_URL: str = "redis://redis:6379"
    CONTENT_SERVICE_URL: str = "http://content_service:8001/v1/content"
    BOS_URL: str = Field(
        default="http://batch_orchestrator_service:5000",
        description="Batch Orchestrator Service URL for pipeline state queries",
    )
    ESSAY_CONTENT_PROVISIONED_TOPIC: str = topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED)
    HTTP_PORT: int = 7001
    PROMETHEUS_PORT: int = 9092
    HOST: str = "0.0.0.0"

    # Content validation settings
    CONTENT_VALIDATION_ENABLED: bool = True
    MIN_CONTENT_LENGTH: int = 50
    MAX_CONTENT_LENGTH: int = 50000
    VALIDATION_LOG_LEVEL: str = "INFO"

    # File validation settings
    ALLOWED_MIME_TYPES: set[str] = Field(
        default={
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
            "application/msword",  # .doc
            "text/plain",  # .txt
            "application/pdf",  # .pdf
        },
        description="Allowed MIME types for file validation",
    )

    # Kafka topic for validation failures (will be implemented with new enum)
    ESSAY_VALIDATION_FAILED_TOPIC: str = topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED)

    # File management event topics
    BATCH_FILE_ADDED_TOPIC: str = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    BATCH_FILE_REMOVED_TOPIC: str = topic_name(ProcessingEvent.BATCH_FILE_REMOVED)

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

    # Outbox configuration is handled by the library's OutboxProvider based on ENVIRONMENT
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="FILE_SERVICE_",
    )

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os

        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("FILE_SERVICE_DATABASE_URL")
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
                f"{prod_host}:{prod_port}/huleedu_file_service"
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
                f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5439/huleedu_file_service"
            )

    @property
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os

        return os.getenv("HULEEDU_DB_USER", "huleedu_user")


# Create a single instance for the application to use
settings = Settings()
