"""
Configuration module for the HuleEdu Essay Lifecycle Service.

This module defines the settings and configuration for the Essay Lifecycle Service,
including Kafka connection settings, HTTP API configuration, and state persistence settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Essay Lifecycle Service.

    Settings are loaded from .env files and environment variables.
    """

    # Service Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development, production, testing
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
    BATCH_SERVICE_URL: str = "http://batch_service:8000/v1"

    # State Storage Configuration
    DATABASE_PATH: str = "./essay_lifecycle.db"
    DATABASE_TIMEOUT: float = 30.0
    DATABASE_POOL_SIZE: int = 20

    # Observability Configuration
    PROMETHEUS_PORT: int = 9090
    ENABLE_METRICS: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="ESSAY_LIFECYCLE_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
