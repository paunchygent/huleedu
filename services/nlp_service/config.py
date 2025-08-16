"""Configuration for NLP Service."""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


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
    DB_NAME: str = "huleedu_nlp"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONSUMER_GROUP: str = "nlp-service-consumer-group"
    CONSUMER_CLIENT_ID: str = "nlp-service-consumer"
    PRODUCER_CLIENT_ID: str = "nlp-service-producer"

    # Kafka Topics - REMOVED: Use topic_name() function instead of hardcoded topics

    # External Service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000"
    CLASS_MANAGEMENT_SERVICE_URL: str = "http://class_management_service:5002"
    LANGUAGE_TOOL_SERVICE_URL: str = Field(
        default="http://language_tool_service:8080",
        description="Language Tool Service URL for grammar checking",
    )

    # Redis Configuration
    REDIS_URL: str = "redis://redis:6379"

    # Metrics Configuration
    PROMETHEUS_PORT: int = 9099

    # Outbox Pattern Configuration
    OUTBOX_POLLING_INTERVAL: int = Field(default=5, description="Seconds between outbox polls")
    OUTBOX_BATCH_SIZE: int = Field(default=100, description="Max events per relay batch")

    # Student Matching Configuration
    EXTRACTION_CONFIDENCE_THRESHOLD: float = Field(
        default=0.7, description="Confidence to exit extraction pipeline early"
    )
    EXTRACTION_MAX_STRATEGIES: int = Field(
        default=3, description="Max strategies to try before giving up"
    )

    # Roster Matching Thresholds
    MATCH_NAME_FUZZY_THRESHOLD: float = Field(
        default=0.7, description="Minimum similarity for fuzzy name match"
    )
    MATCH_EMAIL_FUZZY_THRESHOLD: float = Field(
        default=0.9, description="Minimum similarity for fuzzy email match"
    )
    MATCH_NAME_EXACT_CONFIDENCE: float = Field(
        default=0.95, description="Confidence score for exact name matches"
    )
    MATCH_EMAIL_EXACT_CONFIDENCE: float = Field(
        default=0.98, description="Confidence score for exact email matches"
    )
    MATCH_NAME_PARTIAL_CONFIDENCE: float = Field(
        default=0.85, description="Confidence score for partial name matches (first+last only)"
    )
    MATCH_NAME_FUZZY_CONFIDENCE: float = Field(
        default=0.75, description="Confidence score for fuzzy name matches"
    )
    MATCH_EMAIL_FUZZY_CONFIDENCE: float = Field(
        default=0.88, description="Confidence score for fuzzy email matches"
    )

    # Extraction Patterns (configurable)
    HEADER_PATTERNS: list[str] = Field(
        default=[
            r"Name:\s*(.+)",
            r"Student:\s*(.+)",
            r"Author:\s*(.+)",
            r"By:\s*(.+)",
            r"Submitted by:\s*(.+)",
            r"Written by:\s*(.+)",
            r"Namn:\s*(.+)",  # Swedish
            r"Elev:\s*(.+)",  # Swedish for "Student"
        ],
        description="Regex patterns for extracting names from headers",
    )

    EMAIL_CONTEXT_WINDOW: int = Field(
        default=50, description="Characters to search around email for name"
    )

    # Roster Cache Configuration
    ROSTER_CACHE_TTL: int = Field(
        default=3600, description="Seconds to cache class rosters (1 hour)"
    )

    @property
    def database_url(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations.

        Environment-aware database connection:
        - DEVELOPMENT: Docker container (localhost with unique port)
        - PRODUCTION: External managed database
        """
        import os

        # Check for explicit override first (Docker environment, manual config)
        env_url = os.getenv("NLP_SERVICE_DATABASE_URL")
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
                f"{prod_host}:{prod_port}/huleedu_nlp"
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

            return f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5440/huleedu_nlp"

    @property
    def _db_user(self) -> str:
        """Database user for production connections."""
        import os

        return os.getenv("HULEEDU_DB_USER", "huleedu_user")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="NLP_SERVICE_",
    )


settings = Settings()
