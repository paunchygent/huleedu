from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_", extra="ignore")

    # Service identity
    SERVICE_NAME: str = "identity_service"
    SERVICE_VERSION: str = "0.1.0"

    # HTTP
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )

    # Redis / Kafka
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9092")

    # JWT configuration
    JWT_DEV_SECRET: SecretStr = Field(
        default=SecretStr("dev-secret-change-me"),
        description="JWT signing secret for development environment",
    )
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS: int = 3600

    # RS256 / JWKS (prod)
    JWT_RS256_PRIVATE_KEY_PATH: SecretStr | None = Field(
        default=None, description="Path to RS256 private key for production JWT signing"
    )
    JWT_RS256_PUBLIC_JWKS_KID: str | None = None

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.ENVIRONMENT == Environment.TESTING

    def get_jwt_secret(self) -> SecretStr:
        """Get environment-appropriate JWT secret."""
        if self.is_production() and self.JWT_RS256_PRIVATE_KEY_PATH:
            # Production uses RS256 with private key
            return self.JWT_RS256_PRIVATE_KEY_PATH
        return self.JWT_DEV_SECRET

    def __str__(self) -> str:
        """Secure string representation that masks sensitive data."""
        return (
            f"{self.__class__.__name__}("
            f"service={self.SERVICE_NAME}, "
            f"version={self.SERVICE_VERSION}, "
            f"environment={self.ENVIRONMENT.value}, "
            f"secrets=***MASKED***)"
        )

    def __repr__(self) -> str:
        """Secure repr for debugging that masks sensitive data."""
        return self.__str__()

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Environment-aware database connection as per Rule 085:
        - If SERVICE_DATABASE_URL is set, use it (Docker/Prod override)
        - Production: derive from HULEEDU_PROD_DB_* variables
        - Development: use localhost with per-service port and .env creds
        """
        import os

        # Override for containerized/prod usage
        env_url = os.getenv("IDENTITY_SERVICE_DATABASE_URL") or os.getenv("SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        if self.is_production():
            prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
            prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
            prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD")
            db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
            if not all([prod_host, prod_password]):
                raise ValueError(
                    "Production environment requires HULEEDU_PROD_DB_HOST and "
                    "HULEEDU_PROD_DB_PASSWORD."
                )
            return f"postgresql+asyncpg://{db_user}:{prod_password}@{prod_host}:{prod_port}/huleedu_identity"
        else:
            # Development: local Docker DB port (next available slot)
            db_user_env = os.getenv("HULEEDU_DB_USER")
            db_password_env = os.getenv("HULEEDU_DB_PASSWORD")

            if not db_user_env or not db_password_env:
                raise ValueError(
                    "Missing required database credentials. Ensure HULEEDU_DB_USER and "
                    "HULEEDU_DB_PASSWORD are set in .env."
                )

            # Type narrowing after validation - mypy now knows these are not None
            return f"postgresql+asyncpg://{db_user_env}:{db_password_env}@localhost:5442/huleedu_identity"

    def get_database_url_masked(self) -> str:
        """Return database URL with masked password for logging."""
        return self.database_url_masked(self.database_url)


settings = Settings()
