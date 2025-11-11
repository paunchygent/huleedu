"""Unit tests for config environment variable loading with AliasChoices.

Tests verify that API keys can be loaded from either:
1. Prefixed format: LLM_PROVIDER_SERVICE_*_API_KEY (Docker container)
2. Unprefixed format: *_API_KEY (backward compatibility)

This follows the architectural pattern established in API Gateway service.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from services.llm_provider_service.config import Settings


class TestAPIKeyEnvironmentLoading:
    """Test API key loading from environment variables with multiple naming patterns."""

    def test_openai_key_loads_from_prefixed_env_var(self) -> None:
        """OpenAI API key should load from LLM_PROVIDER_SERVICE_OPENAI_API_KEY (Docker pattern)."""
        test_key = "sk-test-prefixed-key-12345"

        with patch.dict(os.environ, {"LLM_PROVIDER_SERVICE_OPENAI_API_KEY": test_key}, clear=True):
            settings = Settings()

            assert settings.OPENAI_API_KEY.get_secret_value() == test_key

    def test_openai_key_loads_from_unprefixed_env_var(self) -> None:
        """OpenAI API key should load from OPENAI_API_KEY (backward compatibility)."""
        test_key = "sk-test-unprefixed-key-67890"

        with patch.dict(os.environ, {"OPENAI_API_KEY": test_key}, clear=True):
            settings = Settings()

            assert settings.OPENAI_API_KEY.get_secret_value() == test_key

    def test_openai_key_prefers_prefixed_over_unprefixed(self) -> None:
        """When both env vars set, prefixed takes precedence (Docker priority)."""
        prefixed_key = "sk-test-prefixed-priority"
        unprefixed_key = "sk-test-unprefixed-fallback"

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER_SERVICE_OPENAI_API_KEY": prefixed_key,
                "OPENAI_API_KEY": unprefixed_key,
            },
            clear=True,
        ):
            settings = Settings()

            # Prefixed should win
            assert settings.OPENAI_API_KEY.get_secret_value() == prefixed_key

    def test_anthropic_key_loads_from_both_patterns(self) -> None:
        """Anthropic API key supports both prefixed and unprefixed patterns."""
        prefixed_key = "sk-ant-prefixed-test"

        # Test prefixed
        with patch.dict(
            os.environ, {"LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY": prefixed_key}, clear=True
        ):
            settings = Settings()
            assert settings.ANTHROPIC_API_KEY.get_secret_value() == prefixed_key

        # Test unprefixed
        unprefixed_key = "sk-ant-unprefixed-test"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": unprefixed_key}, clear=True):
            settings = Settings()
            assert settings.ANTHROPIC_API_KEY.get_secret_value() == unprefixed_key

    def test_google_key_loads_from_both_patterns(self) -> None:
        """Google API key supports both prefixed and unprefixed patterns."""
        prefixed_key = "google-prefixed-test-key"

        # Test prefixed
        with patch.dict(
            os.environ, {"LLM_PROVIDER_SERVICE_GOOGLE_API_KEY": prefixed_key}, clear=True
        ):
            settings = Settings()
            assert settings.GOOGLE_API_KEY.get_secret_value() == prefixed_key

        # Test unprefixed
        unprefixed_key = "google-unprefixed-test-key"
        with patch.dict(os.environ, {"GOOGLE_API_KEY": unprefixed_key}, clear=True):
            settings = Settings()
            assert settings.GOOGLE_API_KEY.get_secret_value() == unprefixed_key

    def test_openrouter_key_loads_from_both_patterns(self) -> None:
        """OpenRouter API key supports both prefixed and unprefixed patterns."""
        prefixed_key = "sk-or-prefixed-test"

        # Test prefixed
        with patch.dict(
            os.environ, {"LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY": prefixed_key}, clear=True
        ):
            settings = Settings()
            assert settings.OPENROUTER_API_KEY.get_secret_value() == prefixed_key

        # Test unprefixed
        unprefixed_key = "sk-or-unprefixed-test"
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": unprefixed_key}, clear=True):
            settings = Settings()
            assert settings.OPENROUTER_API_KEY.get_secret_value() == unprefixed_key

    def test_all_keys_default_to_empty_when_not_set(self) -> None:
        """When no env vars set, API keys default to empty SecretStr."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

            assert settings.OPENAI_API_KEY.get_secret_value() == ""
            assert settings.ANTHROPIC_API_KEY.get_secret_value() == ""
            assert settings.GOOGLE_API_KEY.get_secret_value() == ""
            assert settings.OPENROUTER_API_KEY.get_secret_value() == ""

    def test_cli_check_models_can_load_keys(self) -> None:
        """Verify CLI check-models command can load API keys correctly."""
        test_openai_key = "sk-test-cli-key"

        # Simulate running CLI outside Docker with unprefixed key
        with patch.dict(os.environ, {"OPENAI_API_KEY": test_openai_key}, clear=True):
            settings = Settings()
            api_key = settings.OPENAI_API_KEY.get_secret_value()

            # This is what CheckerFactory._create_openai_checker checks
            assert api_key != ""
            assert api_key == test_openai_key


class TestDockerEnvironmentSimulation:
    """Test configuration loading in Docker container environment."""

    def test_docker_compose_prefixed_pattern(self) -> None:
        """Simulate docker-compose.yml passing prefixed env vars to container."""
        # docker-compose.yml has:
        # - LLM_PROVIDER_SERVICE_OPENAI_API_KEY=${OPENAI_API_KEY}
        # This means docker-compose reads OPENAI_API_KEY from .env
        # and passes it to container as LLM_PROVIDER_SERVICE_OPENAI_API_KEY

        docker_env = {
            "LLM_PROVIDER_SERVICE_OPENAI_API_KEY": "sk-docker-openai",
            "LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY": "sk-docker-anthropic",
            "LLM_PROVIDER_SERVICE_GOOGLE_API_KEY": "google-docker",
            "LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY": "sk-docker-openrouter",
        }

        with patch.dict(os.environ, docker_env, clear=True):
            settings = Settings()

            assert settings.OPENAI_API_KEY.get_secret_value() == "sk-docker-openai"
            assert settings.ANTHROPIC_API_KEY.get_secret_value() == "sk-docker-anthropic"
            assert settings.GOOGLE_API_KEY.get_secret_value() == "google-docker"
            assert settings.OPENROUTER_API_KEY.get_secret_value() == "sk-docker-openrouter"


class TestBackwardCompatibility:
    """Test backward compatibility with existing .env files."""

    def test_local_env_file_unprefixed_pattern(self) -> None:
        """Simulate local development with unprefixed .env file."""
        # Local .env has: OPENAI_API_KEY=sk-...
        # Settings should read it via AliasChoices fallback

        local_env = {
            "OPENAI_API_KEY": "sk-local-openai",
            "ANTHROPIC_API_KEY": "sk-local-anthropic",
            "GOOGLE_API_KEY": "google-local",
            "OPENROUTER_API_KEY": "sk-local-openrouter",
        }

        with patch.dict(os.environ, local_env, clear=True):
            settings = Settings()

            assert settings.OPENAI_API_KEY.get_secret_value() == "sk-local-openai"
            assert settings.ANTHROPIC_API_KEY.get_secret_value() == "sk-local-anthropic"
            assert settings.GOOGLE_API_KEY.get_secret_value() == "google-local"
            assert settings.OPENROUTER_API_KEY.get_secret_value() == "sk-local-openrouter"
