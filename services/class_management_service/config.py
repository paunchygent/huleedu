from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Class Management Service.

    These settings can be overridden via environment variables prefixed with
    CLASS_MANAGEMENT_SERVICE_.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    SERVICE_NAME: str = "class_management_service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/huledu_class_management"
    PORT: int = 5002
    HOST: str = "0.0.0.0"
    USE_MOCK_REPOSITORY: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CLASS_MANAGEMENT_SERVICE_",
    )


settings = Settings()
