"""Secure base configuration class for HuleEdu services."""

import re
from typing import Optional

from common_core.config_enums import Environment
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class SecureServiceSettings(BaseSettings):
    """Base settings with security defaults and shared configuration for all services.

    This class provides:
    - Secure string representations that mask all secrets
    - Shared environment configuration with proper enum usage
    - Shared database and internal API credentials
    - Helper methods for environment detection
    - Secure database URL handling with password masking
    """

    # Global environment (shared across all services)
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Always read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )

    # Shared database password
    DB_PASSWORD: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="HULEEDU_DB_PASSWORD",
        description="Shared database password for all services",
    )

    # Internal API authentication
    INTERNAL_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="HULEEDU_INTERNAL_API_KEY",
        description="Internal service authentication key",
    )

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self.ENVIRONMENT == Environment.STAGING

    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.ENVIRONMENT == Environment.TESTING

    def requires_security(self) -> bool:
        """Check if environment requires full security measures.

        Production and staging require full security (encrypted secrets, etc.)
        """
        return self.ENVIRONMENT in {Environment.PRODUCTION, Environment.STAGING}

    def __str__(self) -> str:
        """Secure string representation that masks all secrets."""
        return (
            f"{self.__class__.__name__}("
            f"service={getattr(self, 'SERVICE_NAME', 'unknown')}, "
            f"environment={self.ENVIRONMENT.value}, "
            f"secrets=***MASKED***)"
        )

    def __repr__(self) -> str:
        """Secure repr for debugging that masks sensitive data."""
        return self.__str__()

    def database_url_masked(self, database_url: str) -> str:
        """Return database URL with masked password for safe logging.

        Args:
            database_url: The full database URL

        Returns:
            Database URL with password replaced by ***
        """
        # Mask password in URL: user:password@ becomes user:***@
        return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", database_url)

    def get_db_password(self) -> str:
        """Get the database password secret value."""
        return self.DB_PASSWORD.get_secret_value()

    def get_internal_api_key(self) -> str:
        """Get the internal API key secret value."""
        return self.INTERNAL_API_KEY.get_secret_value()

    def get_shared_database_credentials(self) -> dict[str, str]:
        """Get shared database credentials from environment.

        Returns:
            Dictionary with db_user and db_password

        Raises:
            ValueError: If required credentials are missing
        """
        import os

        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = self.get_db_password()

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in .env."
            )

        return {"db_user": db_user, "db_password": db_password}

    def get_production_database_credentials(self) -> dict[str, Optional[str]]:
        """Get production database credentials from environment.

        Returns:
            Dictionary with production database connection details

        Raises:
            ValueError: If required production credentials are missing
        """
        import os

        if not self.is_production():
            raise ValueError(
                "Production credentials should only be accessed in production environment"
            )

        prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
        prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
        prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD")
        db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")

        if not all([prod_host, prod_password]):
            raise ValueError(
                "Production environment requires HULEEDU_PROD_DB_HOST and "
                "HULEEDU_PROD_DB_PASSWORD environment variables"
            )

        return {"host": prod_host, "port": prod_port, "password": prod_password, "user": db_user}

    def build_database_url(
        self,
        *,
        database_name: str,
        service_env_var_prefix: str,
        dev_port: int,
        dev_host: str = "localhost",
        url_encode_password: bool = True,
    ) -> str:
        from .database_utils import build_database_url as _build

        return _build(
            database_name=database_name,
            service_env_var_prefix=service_env_var_prefix,
            is_production=self.is_production(),
            dev_port=dev_port,
            dev_host=dev_host,
            url_encode_password=url_encode_password,
        )
