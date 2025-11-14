"""
Configuration for Batch Conductor Service.

Uses Pydantic settings for environment-based configuration.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from common_core.config_enums import Environment
from huleedu_service_libs.config import SecureServiceSettings

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """Configuration settings for Batch Conductor Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BCS_",
        case_sensitive=False,
        extra="ignore",  # Allow extra environment variables
    )

    # Service identity
    SERVICE_NAME: str = "batch-conductor-service"

    # ENVIRONMENT inherited from SecureServiceSettings with validation_alias for env_prefix
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )

    # Pipeline configuration
    PIPELINE_CONFIG_PATH: str = "pipelines.yaml"

    # HTTP server configuration
    HTTP_HOST: str = Field(default="0.0.0.0", description="HTTP server host")
    HTTP_PORT: int = Field(default=4002, description="HTTP server port")

    # Logging configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Essay Lifecycle Service integration
    ESSAY_LIFECYCLE_SERVICE_URL: str = Field(
        default="http://essay_lifecycle_service:6001",
        description="Base URL for Essay Lifecycle Service API",
    )

    # HTTP client configuration
    HTTP_TIMEOUT: int = Field(default=30, description="HTTP client timeout in seconds")
    HTTP_MAX_RETRIES: int = Field(default=3, description="Maximum HTTP client retries")

    # Repository Configuration (standardized with BOS/ELS)
    USE_MOCK_REPOSITORY: bool = Field(
        default=False, description="Use mock repository for development/testing"
    )

    # Event-driven architecture configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka:9092", description="Kafka bootstrap servers for event consumption"
    )

    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for state caching and idempotency"
    )

    REDIS_TTL_SECONDS: int = Field(
        default=604800,  # 7 days
        description="Redis TTL for essay state data in seconds",
    )

    # Kafka consumer configuration
    KAFKA_CONSUMER_GROUP_ID: str = Field(
        default="bcs-event-consumer", description="Kafka consumer group ID"
    )

    KAFKA_AUTO_OFFSET_RESET: str = Field(
        default="latest", description="Kafka auto offset reset policy"
    )

    # Database configuration
    DB_HOST: str = Field(default="localhost", description="PostgreSQL host (Docker or external)")
    DB_PORT: int = Field(default=5441, description="PostgreSQL port (5441 for BCS in development)")
    DB_NAME: str = Field(default="huleedu_batch_conductor", description="Database name")
    DB_USER: str = Field(default="huleedu_user", description="Database user")

    # PostgreSQL persistence configuration
    ENABLE_POSTGRES_PERSISTENCE: bool = Field(
        default=True, description="Enable PostgreSQL persistence for phase completions"
    )
    USE_REDIS_FOR_STATE: bool = Field(
        default=True, description="Use Redis as primary state store (PostgreSQL as fallback)"
    )

    # Database connection pool configuration
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600  # 1 hour

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        """Return the PostgreSQL database URL for both runtime and migrations.

        Uses shared database URL helper to construct environment-aware connection strings.
        Automatically handles password encoding and production/development environments.
        """
        import os

        # Determine host and port based on ENV_TYPE
        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("BCS_DB_HOST", "batch_conductor_db")
            dev_port_str = os.getenv("BCS_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5441"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_batch_conductor",
            service_env_var_prefix="BCS",
            dev_port=dev_port,
            dev_host=dev_host,
        )


# Global settings instance
settings = Settings()
