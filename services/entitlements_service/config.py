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

    # Metrics port (inherited from SecureServiceSettings but can override)
    METRICS_PORT: int = 8083

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
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os

        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("ENTITLEMENTS_SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        # Environment-based configuration
        if self.is_production():
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
                f"{prod_host}:{prod_port}/huleedu_entitlements"
            )
        else:
            # Development: Docker container (port 5444 for entitlements DB)
            db_user = os.getenv("HULEEDU_DB_USER")
            db_password = os.getenv("HULEEDU_DB_PASSWORD")

            if not db_user or not db_password:
                raise ValueError(
                    "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                    "HULEEDU_DB_PASSWORD are set in your .env file."
                )

            return (
                f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5444/huleedu_entitlements"
            )

    @property
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os

        return os.getenv("HULEEDU_DB_USER", "huleedu_user")
