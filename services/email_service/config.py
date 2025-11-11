"""Configuration settings for Email Service.

This module provides configuration management following SecureServiceSettings pattern.
Environment variables are prefixed with 'EMAIL_' for service isolation.
"""

from __future__ import annotations

from typing import Literal

from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """Configuration settings for Email Service."""

    model_config = SettingsConfigDict(env_prefix="EMAIL_", extra="ignore")

    SERVICE_NAME: str = "email_service"

    # Email provider configuration
    EMAIL_PROVIDER: Literal["mock", "smtp"] = "mock"

    # SMTP Configuration (Namecheap Private Email)
    SMTP_HOST: str = "mail.privateemail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT: int = 30

    # Template configuration
    TEMPLATE_PATH: str = "templates"
    DEFAULT_FROM_EMAIL: str = "noreply@hule.education"
    DEFAULT_FROM_NAME: str = "HuleEdu"

    # Email processing settings
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: int = 60

    # Mock provider settings (for testing)
    MOCK_PROVIDER_FAILURE_RATE: float = 0.0  # Default 0% for deterministic tests

    # Metrics port (inherited from SecureServiceSettings but can override)
    METRICS_PORT: int = 8080

    # Database Connection Pool Settings (following established patterns)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600

    # Infrastructure configuration
    REDIS_URL: str = "redis://redis:6379/0"  # Docker service name
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"  # Docker service name
    PRODUCER_CLIENT_ID_EMAIL: str = "email-service-producer"

    # Circuit breaker configuration
    CIRCUIT_BREAKER_ENABLED: bool = True
    KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30  # seconds
    KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2

    # Logging configuration
    LOG_LEVEL: str = "INFO"

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("EMAIL_SERVICE_DB_HOST", "email_db")
            dev_port_str = os.getenv("EMAIL_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5443"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_email",
            service_env_var_prefix="EMAIL_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )
