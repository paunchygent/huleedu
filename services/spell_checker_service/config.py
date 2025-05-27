"""
Configuration module for the HuleEdu Spell Checker Service.

This module defines the settings and configuration for the Spell Checker Service,
including Kafka connection settings, service URLs, and consumer/producer configurations.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the Spell Checker Service.

    Settings are loaded from .env files and environment variables.
    """

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development, production, testing
    SERVICE_NAME: str = "spell-checker-service"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"
    CONSUMER_GROUP: str = "spellchecker-service-group-v1.1"
    PRODUCER_CLIENT_ID: str = "spellchecker-service-producer"
    CONSUMER_CLIENT_ID: str = "spellchecker-service-consumer"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SPELL_CHECKER_SERVICE_",  # To prefix env vars
    )


# Create a single instance for the application to use
settings = Settings()
