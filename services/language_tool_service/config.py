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

    # Java and LanguageTool server configuration
    LANGUAGE_TOOL_PORT: int = Field(
        default=8081, description="Internal port for LanguageTool server"
    )
    LANGUAGE_TOOL_HEAP_SIZE: str = Field(
        default="512m", description="JVM heap size for LanguageTool"
    )
    LANGUAGE_TOOL_JAR_PATH: str = Field(
        default="/app/languagetool/languagetool-server.jar",
        description="Path to LanguageTool server JAR file",
    )
    LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS: int = Field(
        default=10, description="Maximum concurrent requests to LanguageTool"
    )
    LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS: int = Field(
        default=30, description="Timeout for individual LanguageTool requests"
    )
    LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL: int = Field(
        default=30, description="Interval between health checks in seconds"
    )

    # Category filtering configuration
    GRAMMAR_CATEGORIES_ALLOWED: list[str] = Field(
        default_factory=lambda: [
            "GRAMMAR",
            "CONFUSED_WORDS",
            "AGREEMENT",
            "PUNCTUATION",
            "REDUNDANCY",
            "STYLE",
        ],
        description="Grammar categories to include in results",
    )
    GRAMMAR_CATEGORIES_BLOCKED: list[str] = Field(
        default_factory=lambda: [],
        description="Grammar categories to filter out from results",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LANGUAGE_TOOL_SERVICE_",
    )


# Create a single instance for the application to use
settings = Settings()
