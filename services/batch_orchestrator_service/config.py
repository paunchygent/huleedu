"""
Configuration module for the HuleEdu Batch Orchestrator Service.

This module defines the settings and configuration for the Batch Orchestrator Service,
including environment-specific overrides and Pydantic-based settings validation.
"""

from __future__ import annotations

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # To prefix env vars, e.g. BATCH_ORCHESTRATOR_SERVICE_LOG_LEVEL
        env_prefix="BATCH_ORCHESTRATOR_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
