"""
Configuration module for the HuleEdu Essay Lifecycle Service.

This module defines the settings and configuration for the Essay Lifecycle Service,
including Kafka connection settings, HTTP API configuration, and state persistence settings.
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
    Configuration settings for the Essay Lifecycle Service.

    Settings are loaded from .env files and environment variables.
    """

    # Service Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "essay-lifecycle-service"

    # HTTP API Configuration
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000
    API_VERSION: str = "v1"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers for event consumption and publishing",
    )
    CONSUMER_GROUP: str = "essay-lifecycle-service-group-v1.0"
    PRODUCER_CLIENT_ID: str = "essay-lifecycle-service-producer"
    CONSUMER_CLIENT_ID: str = "essay-lifecycle-service-consumer"

    # External Service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    BATCH_ORCHESTRATOR_SERVICE_URL: str = "http://batch_orchestrator_service:8000/v1"

    # Repository Configuration (three-tier pattern)
    USE_MOCK_REPOSITORY: bool = True  # False in production

    # PostgreSQL Configuration (production)
    DATABASE_HOST: str = Field(default="essay_lifecycle_db", alias="ELS_DB_HOST")
    DATABASE_PORT: int = Field(default=5432, alias="ELS_DB_PORT")
    DATABASE_NAME: str = Field(default="huleedu_essay_lifecycle", alias="ELS_DB_NAME")

    # PostgreSQL Connection Pool Settings
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis URL for state management and idempotency",
    )

    # Observability Configuration
    ENABLE_METRICS: bool = True

    # Testing Configuration
    DISABLE_IDEMPOTENCY: bool = Field(
        default=False, description="Disable idempotency for testing purposes"
    )

    # Slot Assignment Optimization
    USE_ADVISORY_LOCKS_FOR_ASSIGNMENT: bool = Field(
        default=False,
        description=(
            "Use transaction-scoped PostgreSQL advisory locks keyed by (batch_id, text_storage_id) "
            "to serialize duplicate content assignments and reduce tail latency."
        ),
    )

    # Essay States as Inventory (Option B)
    # Deprecated: Option B is always used in service code; flag retained for compatibility only.
    ELS_USE_ESSAY_STATES_AS_INVENTORY: bool = Field(
        default=True,
        description=(
            "[DEPRECATED] essay_states is always used; flag retained for compatibility only."
        ),
    )

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

    # Redis Configuration for Distributed Coordination
    redis_transaction_retries: int = Field(
        default=5, description="Maximum retries for Redis transaction operations"
    )

    # Outbox configuration is handled by the library's OutboxProvider based on ENVIRONMENT

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="ESSAY_LIFECYCLE_SERVICE_",
    )

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Uses shared database URL helper to construct environment-aware connection strings.
        Automatically handles password encoding and production/development environments.
        """
        import os

        # Determine host and port based on ENV_TYPE
        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("ELS_DB_HOST", "essay_lifecycle_db")
            dev_port_str = os.getenv("ELS_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5433"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_essay_lifecycle",
            service_env_var_prefix="ESSAY_LIFECYCLE_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )


# Create a single instance for the application to use
settings = Settings()
