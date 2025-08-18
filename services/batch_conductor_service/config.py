"""
Configuration for Batch Conductor Service.

Uses Pydantic settings for environment-based configuration.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core.config_enums import Environment

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """Configuration settings for Batch Conductor Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BCS_",
        case_sensitive=False,
        extra="ignore",  # Allow extra environment variables
    )

    # Service identity
    SERVICE_NAME: str = "batch-conductor-service"

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

    # Environment type (read without BCS_ prefix to match docker-compose)
    ENV_TYPE: str = Field(
        default="development", description="Environment type", validation_alias="ENV_TYPE"
    )

    # Repository Configuration (standardized with BOS/ELS)
    USE_MOCK_REPOSITORY: bool = Field(
        default=False, description="Use mock repository for development/testing"
    )
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

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

    @property
    def _db_user(self) -> str:
        """Get database user from environment or config."""
        import os

        return os.getenv("HULEEDU_DB_USER", self.DB_USER)

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os

        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("BCS_DATABASE_URL")
        if env_url:
            return env_url

        # Environment-based configuration
        if self.ENVIRONMENT == Environment.PRODUCTION:
            # Production: External managed database
            prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
            prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
            prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD")

            if not all([prod_host, prod_password]):
                raise ValueError(
                    "Production environment requires HULEEDU_PROD_DB_HOST and "
                    "HULEEDU_PROD_DB_PASSWORD environment variables"
                )

            return (
                f"postgresql+asyncpg://{self._db_user}:{prod_password}@"
                f"{prod_host}:{prod_port}/{self.DB_NAME}"
            )
        else:
            # Development: Docker container (existing pattern)
            db_user = os.getenv("HULEEDU_DB_USER")
            db_password = os.getenv("HULEEDU_DB_PASSWORD")

            if not db_user or not db_password:
                raise ValueError(
                    "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                    "HULEEDU_DB_PASSWORD are set in your .env file."
                )

            # Check if we're running inside Docker
            if os.getenv("ENV_TYPE") == "docker":
                # Inside Docker: use container name
                host = os.getenv("BCS_DB_HOST", "batch_conductor_db")
                port = os.getenv("BCS_DB_PORT", "5432")
            else:
                # Local development: use configured host/port
                host = self.DB_HOST
                port = str(self.DB_PORT)

            return f"postgresql+asyncpg://{db_user}:{db_password}@{host}:{port}/{self.DB_NAME}"


# Global settings instance
settings = Settings()
