"""
Configuration module for the HuleEdu Content Service.

This module defines the settings and configuration for the Content Service,
including storage paths, logging levels, and service ports.
"""

from __future__ import annotations

from pathlib import Path

from common_core.config_enums import Environment
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(SecureServiceSettings):
    """
    Configuration settings for the Content Service.

    Settings are loaded from .env files and environment variables.
    """

    # Service identity
    SERVICE_NAME: str = "content-service"

    LOG_LEVEL: str = "INFO"
    # ENVIRONMENT inherited from SecureServiceSettings with validation_alias
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )
    CONTENT_STORE_ROOT_PATH: Path = Path("./.local_content_store_mvp")
    HOST: str = "0.0.0.0"
    PORT: int = 8001  # Default port, matches docker-compose and pdm dev script for content_service
    WEB_CONCURRENCY: int = 4  # Increased from 1 to handle concurrent batch requests

    # Quart app.run() parameters
    DEBUG: bool = False
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CONTENT_SERVICE_",  # To prefix env vars, e.g. CONTENT_SERVICE_LOG_LEVEL
    )


# Create a single instance for the application to use
settings = Settings()
