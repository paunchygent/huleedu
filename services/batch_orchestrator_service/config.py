"""
Configuration module for the HuleEdu Batch Orchestrator Service.

This module defines the settings and configuration for the Batch Orchestrator Service,
including environment-specific overrides and Pydantic-based settings validation.
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
    Configuration settings for the Batch Orchestrator Service.

    These settings can be overridden via environment variables prefixed with
    BATCH_ORCHESTRATOR_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT")
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
    DB_PORT: int = Field(default=5438, validation_alias="BATCH_ORCHESTRATOR_DB_PORT")
    DB_NAME: str = Field(
        default="batch_orchestrator",
        validation_alias="BATCH_ORCHESTRATOR_DB_NAME",
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

    # Circuit Breaker Configuration
    CIRCUIT_BREAKER_ENABLED: bool = Field(
        default=True, description="Enable circuit breaker protection for external service calls"
    )

    # Batch Conductor Service Circuit Breaker
    BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5, description="Number of failures before opening circuit for BCS calls"
    )
    BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=60, description="Seconds to wait before attempting recovery for BCS"
    )
    BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=2, description="Successful calls needed to close circuit for BCS"
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
        # To prefix env vars, e.g. BATCH_ORCHESTRATOR_SERVICE_LOG_LEVEL
        env_prefix="BATCH_ORCHESTRATOR_SERVICE_",
    )

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Standardized PostgreSQL configuration following HuleEdu pattern.
        Uses environment-specific connection details.
        """
        import os

        # Check for environment variable first (Docker environment)
        env_url = os.getenv("BATCH_ORCHESTRATOR_SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        # Fallback to local development configuration (loaded from .env via dotenv)
        import os

        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        return f"postgresql+asyncpg://{db_user}:{db_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


# Create a single instance for the application to use
settings = Settings()
