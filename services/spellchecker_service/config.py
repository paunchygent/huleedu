"""
Configuration module for the HuleEdu Spell Checker Service.

This module defines the settings and configuration for the Spell Checker Service,
including Kafka connection settings, service URLs, and consumer/producer configurations.
"""

from __future__ import annotations

from pathlib import Path

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """
    Configuration settings for the Spell Checker Service.

    Settings are loaded from .env files and environment variables.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )
    SERVICE_NAME: str = "spellchecker_service"
    VERSION: str = "1.0.0"
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers for event consumption and publishing",
    )
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"

    # Database configuration
    DB_HOST: str = "spellchecker_db"
    DB_PORT: int = 5432
    DB_NAME: str = "huleedu_spellchecker"

    # Redis configuration for idempotency
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for idempotency and caching"
    )

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
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("SPELLCHECKER_SERVICE_DB_HOST", "spellchecker_db")
            dev_port_str = os.getenv("SPELLCHECKER_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5437"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_spellchecker",
            service_env_var_prefix="SPELLCHECKER_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SPELLCHECKER_SERVICE_",  # To prefix env vars
    )


# Create a single instance for the application to use
settings = Settings()
