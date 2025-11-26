"""Configuration settings for Entitlements Service.

This module provides configuration management following SecureServiceSettings pattern.
Environment variables are prefixed with 'ENTITLEMENTS_' for service isolation.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """Configuration settings for Entitlements Service."""

    model_config = SettingsConfigDict(env_prefix="ENTITLEMENTS_", extra="ignore")

    SERVICE_NAME: str = "entitlements_service"

    # Credit system configuration
    USE_MOCK_REPOSITORY: bool = False  # Development/testing flag

    # Policy configuration
    POLICY_FILE: str = "policies/default.yaml"
    POLICY_CACHE_TTL: int = 300  # 5 minutes

    # Rate limiting configuration
    RATE_LIMIT_WINDOW_SECONDS: int = 3600  # Default 1 hour window
    RATE_LIMIT_ENABLED: bool = True

    # Credit system settings
    DEFAULT_USER_CREDITS: int = 50
    DEFAULT_ORG_CREDITS: int = 500
    CREDIT_MINIMUM_BALANCE: int = 0  # Prevent negative balances

    # HTTP server port
    HTTP_PORT: int = 8083

    # Database Connection Pool Settings (following established patterns)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600

    # Infrastructure configuration
    REDIS_URL: str = "redis://redis:6379/0"  # Docker service name
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"  # Docker service name
    PRODUCER_CLIENT_ID: str = "entitlements-service-producer"

    # Circuit breaker configuration
    CIRCUIT_BREAKER_ENABLED: bool = True
    KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30  # seconds
    KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2

    # Logging configuration
    LOG_LEVEL: str = "INFO"

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
            dev_host = "entitlements_db"
            dev_port_str = "5432"
        else:
            dev_host = "localhost"
            dev_port_str = "5444"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_entitlements",
            service_env_var_prefix="ENTITLEMENTS_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )
