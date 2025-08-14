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
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )
    SERVICE_NAME: str = "batch-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
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
        
        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os
        
        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("BATCH_ORCHESTRATOR_SERVICE_DATABASE_URL")
        if env_url:
            return env_url
            
        # Environment-based configuration
        if self.ENVIRONMENT == "production":
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
                
            return f"postgresql+asyncpg://{db_user}:{db_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property        
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os
        return os.getenv("HULEEDU_DB_USER", "huleedu_user")


# Create a single instance for the application to use
settings = Settings()
