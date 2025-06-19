"""
Configuration module for the HuleEdu Batch Orchestrator Service.

This module defines the settings and configuration for the Batch Orchestrator Service,
including environment-specific overrides and Pydantic-based settings validation.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Batch Orchestrator Service.

    These settings can be overridden via environment variables prefixed with
    BATCH_ORCHESTRATOR_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development, production, testing
    SERVICE_NAME: str = "batch-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    PORT: int = 5000  # Default port for batch orchestrator service
    HOST: str = "0.0.0.0"
    WEB_CONCURRENCY: int = 1
    GRACEFUL_TIMEOUT: int = 30
    KEEP_ALIVE_TIMEOUT: int = 5

    # Kafka topic configurations for CJ Assessment integration (Sub-task 2.1.4)
    KAFKA_TOPIC_CJ_INITIATE_COMMAND: str = "huleedu.els.cj_assessment.initiate.command.v1"
    KAFKA_TOPIC_BATCH_PHASE_CONCLUDED: str = "huleedu.els.batch_phase.concluded.v1"
    KAFKA_CONSUMER_GROUP_ID: str = "batch-orchestrator-consumers"

    # Database configuration
    DB_HOST: str = Field(default="localhost", validation_alias="BATCH_ORCHESTRATOR_DB_HOST")
    DB_PORT: int = Field(default=5432, validation_alias="BATCH_ORCHESTRATOR_DB_PORT")
    DB_NAME: str = Field(
        default="batch_orchestrator", validation_alias="BATCH_ORCHESTRATOR_DB_NAME"
    )
    DB_USER: str = Field(default="huleedu_user", validation_alias="BATCH_ORCHESTRATOR_DB_USER")
    DB_PASSWORD: str = Field(
        default="REDACTED_DEFAULT_PASSWORD", validation_alias="BATCH_ORCHESTRATOR_DB_PASSWORD"
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Repository configuration
    USE_MOCK_REPOSITORY: bool = False  # Set to True to use mock repository for testing

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"  # Development/test default

    # Batch Conductor Service Configuration
    BCS_BASE_URL: str = "http://batch_conductor_service:4002"
    BCS_PIPELINE_ENDPOINT: str = "/internal/v1/pipelines/define"
    BCS_REQUEST_TIMEOUT: int = 30  # Timeout in seconds for BCS HTTP requests

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # To prefix env vars, e.g. BATCH_ORCHESTRATOR_SERVICE_LOG_LEVEL
        env_prefix="BATCH_ORCHESTRATOR_SERVICE_",
    )

    @property
    def database_url(self) -> str:
        """Construct the PostgreSQL database URL from configuration settings."""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


# Create a single instance for the application to use
settings = Settings()
