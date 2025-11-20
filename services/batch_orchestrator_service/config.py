"""
Configuration module for the HuleEdu Batch Orchestrator Service.

This module defines the settings and configuration for the Batch Orchestrator Service,
including environment-specific overrides and Pydantic-based settings validation.
"""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """
    Configuration settings for the Batch Orchestrator Service.

    These settings can be overridden via environment variables prefixed with
    BATCH_ORCHESTRATOR_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )
    SERVICE_NAME: str = "batch-service"
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for event publishing"
    )
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    CONTENT_SERVICE_TIMEOUT_SECONDS: int = Field(
        default=5,
        description="Timeout in seconds for Content Service validation requests",
    )
    PORT: int = 5000  # Default port for batch orchestrator service
    HOST: str = "0.0.0.0"
    WEB_CONCURRENCY: int = 1
    GRACEFUL_TIMEOUT: int = 30
    KEEP_ALIVE_TIMEOUT: int = 5

    # Kafka consumer configuration
    KAFKA_CONSUMER_GROUP_ID: str = "batch-orchestrator-consumers"

    # Database configuration
    DB_HOST: str = Field(default="localhost", validation_alias="BATCH_ORCHESTRATOR_DB_HOST")
    DB_PORT: int = Field(default=5438, validation_alias="BATCH_ORCHESTRATOR_DB_PORT")
    DB_NAME: str = Field(
        default="huleedu_batch_orchestrator",
        validation_alias="BATCH_ORCHESTRATOR_DB_NAME",
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Repository configuration
    USE_MOCK_REPOSITORY: bool = False  # Set to True to use mock repository for testing

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for caching and distributed state"
    )

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

    # Entitlements Service configuration
    ENTITLEMENTS_BASE_URL: str = Field(
        default="http://entitlements_service:8083",
        description="Entitlements Service base URL",
    )
    ENTITLEMENTS_HTTP_TIMEOUT_SECONDS: int = Field(
        default=10, description="Entitlements Service HTTP timeout in seconds"
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
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("BATCH_ORCHESTRATOR_SERVICE_DB_HOST", "batch_orchestrator_db")
            dev_port_str = os.getenv("BATCH_ORCHESTRATOR_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5438"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_batch_orchestrator",
            service_env_var_prefix="BATCH_ORCHESTRATOR_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )


# Create a single instance for the application to use
settings = Settings()
