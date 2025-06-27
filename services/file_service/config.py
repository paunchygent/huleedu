"""
Configuration module for the HuleEdu File Service.

This module defines the settings and configuration for the File Service,
including Kafka settings, Content Service URL, and service ports.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core.event_enums import ProcessingEvent, topic_name


class Settings(BaseSettings):
    """
    Configuration settings for the File Service.

    These settings can be overridden via environment variables prefixed with
    FILE_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
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

    # Kafka topic for validation failures (will be implemented with new enum)
    ESSAY_VALIDATION_FAILED_TOPIC: str = "huleedu.file.essay.validation.failed.v1"

    # File management event topics
    BATCH_FILE_ADDED_TOPIC: str = "huleedu.file.batch.file.added.v1"
    BATCH_FILE_REMOVED_TOPIC: str = "huleedu.file.batch.file.removed.v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="FILE_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
