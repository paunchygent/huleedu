from __future__ import annotations

from functools import lru_cache

from common_core.config_enums import Environment
from common_core.event_enums import ProcessingEvent, topic_name
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Service Identity
    SERVICE_NAME: str = Field(default="websocket_service", description="Service identifier")
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT, description="Runtime environment"
    )

    # WebSocket Configuration
    WEBSOCKET_PORT: int = Field(default=8080, description="Port for WebSocket service")
    WEBSOCKET_PING_INTERVAL: int = Field(
        default=30, description="WebSocket ping interval in seconds"
    )
    WEBSOCKET_MAX_CONNECTIONS_PER_USER: int = Field(
        default=5, description="Max concurrent connections per user"
    )
    WEBSOCKET_IDLE_TIMEOUT: int = Field(
        default=300, description="Idle timeout in seconds before closing connection"
    )

    # Redis Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    REDIS_CHANNEL_PREFIX: str = Field(default="ws", description="Prefix for user channels")
    REDIS_CONNECT_TIMEOUT: int = Field(default=5, description="Redis connection timeout in seconds")
    REDIS_SOCKET_TIMEOUT: int = Field(default=5, description="Redis socket timeout in seconds")

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers"
    )
    KAFKA_CONSUMER_GROUP: str = Field(
        default="websocket-service-consumer", description="Kafka consumer group ID"
    )
    KAFKA_CONSUMER_CLIENT_ID: str = Field(
        default="websocket-service-client", description="Kafka consumer client ID"
    )

    @property
    def BATCH_FILE_ADDED_TOPIC(self) -> str:
        """Topic for file added events."""
        return topic_name(ProcessingEvent.BATCH_FILE_ADDED)

    @property
    def BATCH_FILE_REMOVED_TOPIC(self) -> str:
        """Topic for file removed events."""
        return topic_name(ProcessingEvent.BATCH_FILE_REMOVED)

    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-here",  # TODO: Move to secrets manager
        description="Secret key for JWT validation",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")

    # CORS Configuration for WebSocket upgrade
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed origins for CORS",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow credentials in CORS")
    CORS_ALLOW_METHODS: list[str] = Field(
        default_factory=lambda: ["GET", "POST"],
        description="Allowed methods for CORS",
    )
    CORS_ALLOW_HEADERS: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed headers for CORS",
    )

    # Observability
    ENABLE_METRICS: bool = Field(default=True, description="Enable Prometheus metrics")
    ENABLE_TRACING: bool = Field(default=False, description="Enable distributed tracing")
    JAEGER_ENDPOINT: str = Field(
        default="http://jaeger:14268/api/traces",
        description="Jaeger collector endpoint",
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
