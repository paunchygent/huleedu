from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_SERVICE_", extra="ignore")

    # Service identity
    SERVICE_NAME: str = "identity_service"
    SERVICE_VERSION: str = "0.1.0"

    # HTTP
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )

    # Redis / Kafka
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("IDENTITY_SERVICE_REDIS_URL", "IDENTITY_REDIS_URL"),
    )
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        validation_alias=AliasChoices(
            "IDENTITY_SERVICE_KAFKA_BOOTSTRAP_SERVERS", "IDENTITY_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )

    # JWT configuration
    JWT_DEV_SECRET: SecretStr = Field(
        default=SecretStr("dev-secret-change-me"),
        description="JWT signing secret for development environment",
    )
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS: int = 3600
    JWT_ISSUER: str = Field(
        default="huleedu-identity-service",
        description="JWT issuer for tokens minted by Identity",
    )
    JWT_AUDIENCE: str = Field(
        default="huleedu-platform",
        description="Intended audience for platform access tokens",
    )

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
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = (
                os.getenv("IDENTITY_SERVICE_DB_HOST")
                or os.getenv("IDENTITY_DB_HOST")
                or "identity_db"
            )
            dev_port_str = (
                os.getenv("IDENTITY_SERVICE_DB_PORT") or os.getenv("IDENTITY_DB_PORT") or "5432"
            )
        else:
            dev_host = "localhost"
            dev_port_str = "5442"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_identity",
            service_env_var_prefix="IDENTITY_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    def get_database_url_masked(self) -> str:
        """Return database URL with masked password for logging."""
        return self.database_url_masked(self.DATABASE_URL)


settings = Settings()
