from pydantic import model_validator
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
    DB_USER: str = "user"
    DB_PASSWORD: str = "password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "huledu_class_management"
    DATABASE_URL: str | None = None

    @model_validator(mode='before')
    def assemble_db_connection(cls, v):
        if isinstance(v, dict) and v.get('DATABASE_URL') is None:
            v['DATABASE_URL'] = (
                f"postgresql+asyncpg://{v.get('DB_USER')}:{v.get('DB_PASSWORD')}"
                f"@{v.get('DB_HOST')}:{v.get('DB_PORT')}/{v.get('DB_NAME')}"
            )
        return v
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
