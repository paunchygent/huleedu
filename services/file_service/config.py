"""
Configuration module for the HuleEdu File Service.

This module defines the settings and configuration for the File Service,
including Kafka settings, Content Service URL, and service ports.
"""

from __future__ import annotations

from common_core.config_enums import Environment
from common_core.event_enums import ProcessingEvent, topic_name
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """
    Configuration settings for the File Service.

    These settings can be overridden via environment variables prefixed with
    FILE_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )
    SERVICE_NAME: str = "file-service"
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for event publishing"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for caching and distributed locks"
    )
    CONTENT_SERVICE_URL: str = "http://content_service:8001/v1/content"
    BOS_URL: str = Field(
        default="http://batch_orchestrator_service:5000",
        description="Batch Orchestrator Service URL for pipeline state queries",
    )
    ESSAY_CONTENT_PROVISIONED_TOPIC: str = topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED)
    HTTP_PORT: int = 7001
    PROMETHEUS_PORT: int = 9099
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
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("FILE_SERVICE_DB_HOST", "file_service_db")
            dev_port_str = os.getenv("FILE_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5439"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_file_service",
            service_env_var_prefix="FILE_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )


# Create a single instance for the application to use
settings = Settings()
