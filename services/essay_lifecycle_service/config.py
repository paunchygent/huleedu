"""
Configuration module for the HuleEdu Essay Lifecycle Service.

This module defines the settings and configuration for the Essay Lifecycle Service,
including Kafka connection settings, HTTP API configuration, and state persistence settings.
"""

from __future__ import annotations

from pydantic import Field
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
    BATCH_ORCHESTRATOR_SERVICE_URL: str = "http://batch_orchestrator_service:8000/v1"

    # Repository Configuration (following BOS pattern)
    USE_MOCK_REPOSITORY: bool = True  # False in production

    # SQLite Configuration (development/testing)
    DATABASE_PATH: str = "./essay_lifecycle.db"
    DATABASE_TIMEOUT: float = 30.0
    DATABASE_POOL_SIZE: int = 20

    # PostgreSQL Configuration (production)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://huleedu_user:REDACTED_DEFAULT_PASSWORD@essay_lifecycle_db:5432/essay_lifecycle",
        alias="ELS_DATABASE_URL"
    )
    DATABASE_HOST: str = Field(default="essay_lifecycle_db", alias="ELS_DB_HOST")
    DATABASE_PORT: int = Field(default=5432, alias="ELS_DB_PORT")
    DATABASE_NAME: str = Field(default="essay_lifecycle", alias="ELS_DB_NAME")
    DATABASE_USER: str = Field(default="huleedu_user", alias="ELS_DB_USER")
    DATABASE_PASSWORD: str = Field(default="REDACTED_DEFAULT_PASSWORD", alias="ELS_DB_PASSWORD")

    # PostgreSQL Connection Pool Settings
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

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
