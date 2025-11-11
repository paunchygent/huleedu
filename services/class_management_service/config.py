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
    Configuration settings for the Class Management Service.

    These settings can be overridden via environment variables prefixed with
    CLASS_MANAGEMENT_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "class_management_service"
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for event publishing"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for caching and distributed state"
    )

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("CLASS_MANAGEMENT_SERVICE_DB_HOST", "class_management_db")
            dev_port_str = os.getenv("CLASS_MANAGEMENT_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5435"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_class_management",
            service_env_var_prefix="CLASS_MANAGEMENT_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    PORT: int = 5002
    HOST: str = "0.0.0.0"
    USE_MOCK_REPOSITORY: bool = False

    # Database Pool Configuration
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Maximum overflow connections")
    DATABASE_POOL_PRE_PING: bool = Field(default=True, description="Pre-ping connections")
    DATABASE_POOL_RECYCLE: int = Field(
        default=3600, description="Recycle connections after seconds"
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CLASS_MANAGEMENT_SERVICE_",
    )


settings = Settings()
