"""Configuration for NLP Service."""

from __future__ import annotations

from common_core.config_enums import Environment
from dotenv import find_dotenv, load_dotenv
from huleedu_service_libs.config import SecureServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))


class Settings(SecureServiceSettings):
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
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers for event consumption and publishing",
    )
    CONSUMER_GROUP: str = "nlp-service-consumer-group"
    CONSUMER_CLIENT_ID: str = "nlp-service-consumer"
    PRODUCER_CLIENT_ID: str = "nlp-service-producer"

    # Kafka Topics - REMOVED: Use topic_name() function instead of hardcoded topics

    # External Service URLs
    CONTENT_SERVICE_URL: str = "http://content_service:8000"
    CLASS_MANAGEMENT_SERVICE_URL: str = "http://class_management_service:5002"
    LANGUAGE_TOOL_SERVICE_URL: str = Field(
        default="http://language_tool_service:8085",
        description="Language Tool Service URL for grammar checking",
    )

    # Language Tool Client Configuration
    LANGUAGE_TOOL_CIRCUIT_BREAKER_ENABLED: bool = True
    LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30
    LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2
    LANGUAGE_TOOL_REQUEST_TIMEOUT: int = 30
    LANGUAGE_TOOL_MAX_RETRIES: int = 3
    LANGUAGE_TOOL_RETRY_DELAY: float = 0.5

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379", description="Redis URL for caching and distributed state"
    )

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
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("NLP_SERVICE_DB_HOST", "nlp_db")
            dev_port_str = os.getenv("NLP_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5440"

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_nlp",
            service_env_var_prefix="NLP_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="NLP_SERVICE_",
    )


settings = Settings()
