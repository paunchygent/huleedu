"""
Configuration module for the HuleEdu Content Service.

This module defines the settings and configuration for the Content Service,
including storage paths, logging levels, and service ports.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Content Service.

    Settings are loaded from .env files and environment variables.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development, production, testing
    CONTENT_STORE_ROOT_PATH: Path = Path("./.local_content_store_mvp")
    PORT: int = 8001  # Default port, matches docker-compose and pdm dev script for content_service

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CONTENT_SERVICE_",  # To prefix env vars, e.g. CONTENT_SERVICE_LOG_LEVEL
    )


# Create a single instance for the application to use
settings = Settings()
