"""
Configuration module for the HuleEdu Spell Checker Service.

This module defines the settings and configuration for the Spell Checker Service,
including Kafka connection settings, service URLs, and consumer/producer configurations.
"""

from __future__ import annotations

from pathlib import Path

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """
    Configuration settings for the Spell Checker Service.

    Settings are loaded from .env files and environment variables.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "spell-checker-service"
    VERSION: str = "1.0.0"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"

    # Database configuration
    DB_HOST: str = "spellchecker_db"
    DB_PORT: int = 5432
    DB_NAME: str = "spellchecker"

    # Redis configuration for idempotency
    REDIS_URL: str = "redis://redis:6379"

    CONSUMER_GROUP: str = "spellchecker-service-group-v1.1"
    PRODUCER_CLIENT_ID: str = "spellchecker-service-producer"
    CONSUMER_CLIENT_ID: str = "spellchecker-service-consumer"

    # Note: Using aiokafka library defaults for consumer tuning parameters
    # Premature optimizations removed in favor of proven defaults

    # Metrics Configuration
    HTTP_PORT: int = 8002  # Port for health API and Prometheus metrics endpoint

    # L2 Correction Settings - Service-local paths for autonomy
    L2_MASTER_DICT_PATH: str = "./data/l2_error_dict/nortvig_master_SWE_L2_corrections.txt"
    L2_FILTERED_DICT_PATH: str = "./data/l2_error_dict/filtered_l2_dictionary.txt"
    L2_DATA_DIR: str = "./data/l2_error_dict"  # Base directory for L2 data
    ENABLE_L2_CORRECTIONS: bool = True

    # Spell Checker Settings
    DEFAULT_LANGUAGE: str = "en"
    ENABLE_CORRECTION_LOGGING: bool = True
    CORRECTION_LOG_OUTPUT_DIR: str = "data/corrected_essays"
    DATA_DIR: str = "./data"  # Base directory for spell checker data files

    # Parallel Processing Configuration
    ENABLE_PARALLEL_PROCESSING: bool = Field(
        default=True, description="Enable parallel word correction processing"
    )
    MAX_CONCURRENT_CORRECTIONS: int = Field(
        default=10, description="Maximum concurrent word corrections (semaphore limit)"
    )
    SPELLCHECK_BATCH_SIZE: int = Field(
        default=100, description="Maximum words per batch for parallel processing"
    )
    PARALLEL_TIMEOUT_SECONDS: float = Field(
        default=5.0, description="Timeout per word correction in seconds"
    )
    PARALLEL_PROCESSING_MIN_WORDS: int = Field(
        default=5, description="Minimum words to trigger parallel processing"
    )

    # Environment-specific overrides (for containerized deployments)
    L2_EXTERNAL_DATA_PATH: str | None = None  # Override for mounted volumes

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

    @property
    def _service_dir(self) -> Path:
        """Get the service directory path (where this config.py file is located)."""
        return Path(__file__).parent

    @property
    def effective_correction_log_dir(self) -> str:
        """Get effective correction log output directory."""
        return str(self._service_dir / "data" / "corrected_essays")

    @property
    def effective_l2_data_dir(self) -> str:
        """Get effective L2 data directory, supporting external mounts."""
        if self.L2_EXTERNAL_DATA_PATH:
            return self.L2_EXTERNAL_DATA_PATH
        return str(self._service_dir / "data" / "l2_error_dict")

    @property
    def effective_master_dict_path(self) -> str:
        """Get effective master dictionary path."""
        if self.L2_EXTERNAL_DATA_PATH:
            return f"{self.L2_EXTERNAL_DATA_PATH}/nortvig_master_SWE_L2_corrections.txt"
        return str(
            self._service_dir / "data" / "l2_error_dict" / "nortvig_master_SWE_L2_corrections.txt",
        )

    @property
    def effective_filtered_dict_path(self) -> str:
        """Get effective filtered dictionary path."""
        if self.L2_EXTERNAL_DATA_PATH:
            return f"{self.L2_EXTERNAL_DATA_PATH}/filtered_l2_dictionary.txt"
        return str(self._service_dir / "data" / "l2_error_dict" / "filtered_l2_dictionary.txt")

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Standardized PostgreSQL configuration following HuleEdu pattern.
        Uses environment-specific connection details.
        """
        import os

        # Check for environment variable first (Docker environment)
        env_url = os.getenv("SPELLCHECKER_SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        # Fallback to local development configuration (loaded from .env via dotenv)
        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        # For development/migration: map container names to localhost
        host = self.DB_HOST
        port = self.DB_PORT

        # Map container database hosts to localhost for local development
        if host == "spellchecker_db":
            host = "localhost"
            port = 5437  # External port from docker-compose

        return f"postgresql+asyncpg://{db_user}:{db_password}@{host}:{port}/{self.DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SPELLCHECKER_SERVICE_",  # To prefix env vars
    )


# Create a single instance for the application to use
settings = Settings()
