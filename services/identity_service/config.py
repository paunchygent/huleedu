from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
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
    JWT_DEV_SECRET: str = "dev-secret-change-me"
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS: int = 3600

    # RS256 / JWKS (prod)
    JWT_RS256_PRIVATE_KEY_PATH: str | None = None
    JWT_RS256_PUBLIC_JWKS_KID: str | None = None

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

        if str(self.ENVIRONMENT) == "production":
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


settings = Settings()
