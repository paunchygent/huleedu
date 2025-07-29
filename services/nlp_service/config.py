"""Configuration for NLP Service."""

from __future__ import annotations

from common_core.config_enums import Environment
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NLP Service configuration settings."""

    # Service Identity
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    SERVICE_NAME: str = "nlp-service"
    VERSION: str = "0.1.0"

    # Database Configuration
    DB_HOST: str = "nlp_db"
    DB_PORT: int = 5432
    DB_NAME: str = "nlp_service"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONSUMER_GROUP: str = "nlp-service-consumer-group"
    CONSUMER_CLIENT_ID: str = "nlp-service-consumer"
    PRODUCER_CLIENT_ID: str = "nlp-service-producer"

    # External Service URLs
    CONTENT_SERVICE_URL: str = "http://content-service:8003"
    CLASS_MANAGEMENT_SERVICE_URL: str = "http://class-management-service:8005"

    # Redis Configuration
    REDIS_URL: str = "redis://redis:6379"

    # Metrics Configuration
    PROMETHEUS_PORT: int = 9099

    # Outbox Pattern Configuration
    OUTBOX_POLLING_INTERVAL: int = Field(default=5, description="Seconds between outbox polls")
    OUTBOX_BATCH_SIZE: int = Field(default=100, description="Max events per relay batch")

    @property
    def database_url(self) -> str:
        """Return PostgreSQL database URL."""
        import os

        # Check for environment variable first
        env_url = os.getenv("NLP_SERVICE_DATABASE_URL")
        if env_url:
            return env_url

        # Build from components
        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        # Map container names to localhost for local development
        host = self.DB_HOST
        port = self.DB_PORT

        if host == "nlp_db":
            host = "localhost"
            port = 5440  # External port from docker-compose

        return f"postgresql+asyncpg://{db_user}:{db_password}@{host}:{port}/{self.DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="NLP_SERVICE_",
    )


settings = Settings()
