"""
Configuration module for the HuleEdu File Service.

This module defines the settings and configuration for the File Service,
including Kafka settings, Content Service URL, and service ports.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core.enums import ProcessingEvent, topic_name


class Settings(BaseSettings):
    """
    Configuration settings for the File Service.

    These settings can be overridden via environment variables prefixed with
    FILE_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "file-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8001/v1/content"
    ESSAY_CONTENT_READY_TOPIC: str = topic_name(ProcessingEvent.ESSAY_CONTENT_READY)
    HTTP_PORT: int = 7001
    PROMETHEUS_PORT: int = 9092
    HOST: str = "0.0.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="FILE_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
