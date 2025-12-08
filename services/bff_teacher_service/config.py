"""Configuration for BFF Teacher Service.

Uses Pydantic settings for environment-based configuration.
Minimal skeleton for static file serving - API composition settings added later.
"""

from __future__ import annotations

from pathlib import Path

from common_core.config_enums import Environment
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class BFFTeacherSettings(SecureServiceSettings):
    """Configuration settings for BFF Teacher Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BFF_TEACHER_SERVICE_",
        case_sensitive=False,
        extra="ignore",
    )

    # Service identity
    SERVICE_NAME: str = "bff-teacher-service"

    # Environment
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",
        description="Runtime environment for the service",
    )

    # HTTP server configuration
    HOST: str = Field(default="0.0.0.0", description="HTTP server host")
    PORT: int = Field(default=4101, description="HTTP server port")

    # Static file serving
    STATIC_DIR: Path = Field(
        default=Path("/app/static"),
        description="Directory containing frontend static files",
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # CORS configuration for frontend development
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
        description="Allowed CORS origins for Vue 3 frontend dev server",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True, description="Allow credentials in CORS requests"
    )
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS (static serving and API composition)",
    )
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"], description="Allowed headers for CORS requests"
    )


# Global settings instance
settings = BFFTeacherSettings()
