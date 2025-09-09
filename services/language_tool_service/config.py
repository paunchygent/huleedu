"""
Configuration module for the HuleEdu Language Tool Service.

This module defines the settings and configuration for the Language Tool Service,
including HTTP port configuration and Language Tool wrapper settings.
"""

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
    Configuration settings for the Language Tool Service.

    These settings can be overridden via environment variables prefixed with
    LANGUAGE_TOOL_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )
    SERVICE_NAME: str = "language-tool-service"
    HTTP_PORT: int = 8085
    HOST: str = "0.0.0.0"

    # Language Tool configuration
    LANGUAGE_TOOL_TIMEOUT_SECONDS: int = Field(
        default=30, description="Timeout for Language Tool API calls"
    )
    LANGUAGE_TOOL_MAX_RETRIES: int = Field(
        default=3, description="Maximum retries for Language Tool API calls"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LANGUAGE_TOOL_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
