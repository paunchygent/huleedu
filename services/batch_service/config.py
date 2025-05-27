"""
Configuration module for the HuleEdu Batch Service.

This module defines the settings and configuration for the Batch Service,
including service URLs, ports, and Hypercorn server settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Batch Service.

    Settings are loaded from .env files and environment variables.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development, production, testing
    SERVICE_NAME: str = "batch-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    PORT: int = 5000  # Default port for batch service
    HOST: str = "0.0.0.0"
    WEB_CONCURRENCY: int = 1
    GRACEFUL_TIMEOUT: int = 30
    KEEP_ALIVE_TIMEOUT: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="BATCH_SERVICE_",  # To prefix env vars, e.g. BATCH_SERVICE_LOG_LEVEL
    )


# Create a single instance for the application to use
settings = Settings()
