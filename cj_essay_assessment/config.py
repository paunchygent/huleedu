"""Configuration module for the CJ Essay Assessment system.

This module provides Pydantic models for configuration management,
loading settings from both .env and config.yml files.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderDetails(BaseSettings):
    """Configuration for a specific LLM provider.
    Add new fields as needed for each API (e.g., max_tokens, temperature).
    """

    api_base: str | None = None
    max_tokens: int | None = 1024
    temperature: float | None = 0.7
    model_name: str | None = None

    model_config = SettingsConfigDict(extra="allow")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMProviderDetails":
        """Create a LLMProviderDetails instance from a dictionary."""
        return cls(**data)


class Settings(BaseSettings):
    """Main settings class for the application."""

    # Database settings
    database_url: str = "sqlite+aiosqlite:///test.db"

    # Logging
    log_level: str = "INFO"

    # File paths
    essay_input_dir: str = "data/essays"
    cache_directory: str = "cache_data"

    # LLM settings
    default_provider: str = "openrouter"
    comparison_model: str = "openai/gpt-4o"
    temperature: float = 0.7
    max_tokens_response: int = 500
    system_prompt: str = "You are an expert in evaluating essays."
    llm_providers: dict[str, LLMProviderDetails] = Field(default_factory=dict)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    openrouter_api_key: str | None = None

    # LLM Retry Settings (Tenacity)
    llm_retry_enabled: bool = Field(
        True,
        description="Enable or disable retries for LLM calls.",
    )

    # LLM Concurrency
    llm_concurrency_limit: int = Field(
        5,
        gt=0,
        description="Maximum number of concurrent LLM API calls allowed. Controls asyncio.Semaphore in llm_caller.py.",
    )
    llm_retry_attempts: int = Field(
        3,
        gt=0,
        description="Maximum number of retry attempts for LLM calls.",
    )
    llm_retry_wait_min_seconds: float = Field(
        1.0,
        gt=0,
        description="Minimum wait time in seconds for exponential backoff.",
    )
    llm_retry_wait_max_seconds: float = Field(
        10.0,
        gt=0,
        description="Maximum wait time in seconds for exponential backoff.",
    )
    llm_retry_on_exception_names: list[str] = Field(
        default_factory=lambda: [
            "aiohttp.ClientConnectionError",
            "aiohttp.ClientResponseError",
            "asyncio.TimeoutError",
            "aiohttp.ClientOSError",
            "aiohttp.ServerDisconnectedError",
        ],
        description="List of fully qualified exception class names (as strings) to retry on.",
    )
    llm_request_timeout_seconds: int = Field(
        60,
        gt=0,
        description="Timeout for LLM API requests in seconds.",
    )

    # Assessment settings
    max_pairwise_comparisons: int = 500
    score_stability_threshold: float = 0.05
    min_comparisons_for_stability_check: int = 50
    comparisons_per_stability_check_iteration: int = 20
    cache_enabled: bool = True
    cache_type: str = "disk"
    cache_ttl_seconds: int = 86400  # 24 hours
    assessment_prompt_template: str = """
    Please compare the following two essays based on clarity,
    argumentation, evidence, and overall quality.
    Choose which essay is better and provide a justification for your choice.

    Essay A:
    {essay_a_text}

    Essay B:
    {essay_b_text}
    ---
    """

    spell_check_language: str = Field(
        "sv_SE", description="Language tag passed to PyEnchant (e.g. 'sv_SE', 'en_US')."
    )
    use_corrected_text_for_comparison: bool = Field(
        False,
        description="If true, downstream modules should prefer "
        "'text_content_corrected' over 'processed_content'.",
    )

    supported_spell_check_languages: list[str] = ["sv_SE", "en_US", "en_GB"]
    nlp_features_to_compute: list[str] = ["word_count"]

    # For environment file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url")
    def sqlite_to_async(cls, v: str) -> str:  # pylint: disable=E0213
        """Convert SQLite URL to use aiosqlite driver."""
        if v.startswith("sqlite:"):
            # Ensure we don't double-replace if it's already aiosqlite
            # from .env
            if not v.startswith("sqlite+aiosqlite:"):
                return v.replace("sqlite:", "sqlite+aiosqlite:", 1)
        return v

    @property
    def essay_input_path(self) -> Path:
        """Get the path to the essay input directory."""
        os.makedirs(self.essay_input_dir, exist_ok=True)
        return Path(self.essay_input_dir)

    @property
    def cache_directory_path(self) -> Path:
        """Get the path to the cache directory."""
        os.makedirs(self.cache_directory, exist_ok=True)
        return Path(self.cache_directory)


def load_settings() -> Settings:
    """Load settings from environment variables and config.yml.

    Returns:
        Settings: Configured settings instance.

    """
    yaml_config_path = "config.yml"
    yaml_data: dict[str, Any] = {}

    if os.path.exists(yaml_config_path):
        with open(yaml_config_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    # Create settings using explicit environment variables overriding defaults
    env_kwargs: dict[str, Any] = {}
    for field_name in Settings.model_fields.keys():
        env_var = field_name.upper()
        if env_var in os.environ:
            env_kwargs[field_name] = os.environ[env_var]
    temp_settings = Settings(**env_kwargs)

    # Manually overlay YAML values for keys NOT set by environment variables
    # (BaseSettings v2 loads .env first, so we only apply YAML if no
    # env var exists)
    env_vars_set = os.environ

    for key, value in yaml_data.items():
        # Convert Pydantic field name to expected ENV_VAR name convention
        env_var_name = key.upper()

        # If the corresponding environment variable is NOT set,
        # apply the YAML value
        if env_var_name not in env_vars_set:
            # Handle nested configuration for LLM providers specifically
            if key == "llm_providers" and isinstance(value, dict):
                provider_models = {}
                # Convert each provider dictionary to a LLMProviderDetails instance
                for provider_name, provider_config in value.items():
                    if isinstance(provider_config, dict):
                        provider_models[provider_name] = LLMProviderDetails.from_dict(
                            provider_config
                        )
                    else:
                        # In case it's already a model somehow
                        provider_models[provider_name] = provider_config
                setattr(temp_settings, key, provider_models)
            # Check if the key exists in the Settings model before setting
            elif hasattr(temp_settings, key):
                setattr(temp_settings, key, value)

    return temp_settings


def get_settings() -> Settings:
    """Get settings instance.

    This function creates and returns a Settings instance by loading configuration
    from environment variables and config.yml. In production code, you should
    pass the Settings object explicitly to functions and class constructors that
    need it, rather than calling this function directly from within those components.

    Returns:
        Settings: Configured settings instance.
    """
    return load_settings()
