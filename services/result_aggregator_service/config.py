"""Configuration for Result Aggregator Service."""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(BaseSettings):
    """Service configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service Identity
    SERVICE_NAME: str = Field(default="result_aggregator_service")
    SERVICE_VERSION: str = Field(default="1.0.0")
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    # HTTP API Configuration
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=4003)

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.
        
        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os
        
        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("RESULT_AGGREGATOR_SERVICE_DATABASE_URL") 
        if env_url:
            return env_url
            
        # Environment-based configuration
        if self.ENVIRONMENT == "production":
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
                f"{prod_host}:{prod_port}/huleedu_result_aggregator"
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
                f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5436/huleedu_result_aggregator"
            )

    @property        
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os
        return os.getenv("HULEEDU_DB_USER", "huleedu_user")

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
    INTERNAL_API_KEY: str = Field(
        default="dev-internal-api-key", description="Shared secret for service-to-service auth"
    )
    ALLOWED_SERVICE_IDS: list[str] = Field(
        default=["api-gateway-service", "admin-dashboard-service"],
        description="Services allowed to query this API",
    )

    # Monitoring Configuration
    METRICS_PORT: int = Field(default=9096)
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
