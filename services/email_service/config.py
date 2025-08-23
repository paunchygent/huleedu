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
    EMAIL_PROVIDER: Literal["mock", "sendgrid", "ses"] = "mock"
    SENDGRID_API_KEY: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    
    # Template configuration
    TEMPLATE_PATH: str = "templates"
    DEFAULT_FROM_EMAIL: str = "noreply@huleedu.com"
    DEFAULT_FROM_NAME: str = "HuleEdu"
    
    # Email processing settings
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: int = 60
    
    # Metrics port (inherited from SecureServiceSettings but can override)
    METRICS_PORT: int = 8080
    
    # Database Connection Pool Settings (following established patterns)
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_POOL_RECYCLE: int = 3600
    
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
        env_url = os.getenv("EMAIL_SERVICE_DATABASE_URL")
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
                f"{prod_host}:{prod_port}/huleedu_email"
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
            
            return (
                f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5443/huleedu_email"
            )
    
    @property
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os
        
        return os.getenv("HULEEDU_DB_USER", "huleedu_user")