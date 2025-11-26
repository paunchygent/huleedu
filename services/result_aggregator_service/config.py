"""Configuration for Result Aggregator Service."""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
    """Service configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service Identity
    SERVICE_NAME: str = Field(default="result_aggregator_service")
    SERVICE_VERSION: str = Field(default="1.0.0")
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",  # Read from global ENVIRONMENT var
        description="Runtime environment for the service",
    )

    # HTTP API Configuration
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=4003)

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("RESULT_AGGREGATOR_SERVICE_DB_HOST", "result_aggregator_db")
            dev_port_str = os.getenv("RESULT_AGGREGATOR_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5436"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_result_aggregator",
            service_env_var_prefix="RESULT_AGGREGATOR_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9093")
    KAFKA_CONSUMER_GROUP_ID: str = Field(default="result_aggregator_group")
    KAFKA_AUTO_OFFSET_RESET: str = Field(default="earliest")
    KAFKA_MAX_POLL_RECORDS: int = Field(default=100)
    KAFKA_SESSION_TIMEOUT_MS: int = Field(default=30000)

    # Redis Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_CACHE_TTL_SECONDS: int = Field(default=300)  # 5 minutes
    REDIS_IDEMPOTENCY_TTL_SECONDS: int = Field(default=86400)  # 24 hours

    # Security Configuration
    # INTERNAL_API_KEY inherited from SecureServiceSettings as SecretStr
    ALLOWED_SERVICE_IDS: list[str] = Field(
        default=["api-gateway-service", "admin-dashboard-service"],
        description="Services allowed to query this API",
    )

    # Monitoring Configuration
    LOG_LEVEL: str = Field(default="INFO")

    # Performance Configuration
    API_TIMEOUT_SECONDS: int = Field(default=30)
    CACHE_ENABLED: bool = Field(default=True)

    # Batch Orchestrator Service Configuration
    BOS_URL: str = Field(
        default="http://localhost:4001", description="Batch Orchestrator Service URL"
    )
    BOS_TIMEOUT_SECONDS: int = Field(default=10, description="BOS HTTP client timeout")

    # Error Handling Configuration
    RAISE_ON_DESERIALIZATION_ERROR: bool = Field(
        default=False,
        description="If True, consumer will raise exceptions on bad data. For testing only.",
    )
    STORE_POISON_PILLS: bool = Field(
        default=True,
        description="If True, store malformed messages in Redis for manual inspection.",
    )
    POISON_PILL_TTL_SECONDS: int = Field(
        default=86400,  # 24 hours
        description="How long to keep poison pills in Redis.",
    )


settings = Settings()
