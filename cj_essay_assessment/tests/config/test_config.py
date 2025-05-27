# mypy: disable-error-code=call-arg
"""Tests for configuration management module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import yaml

from src.cj_essay_assessment.config import (LLMProviderDetails, Settings,
                                            get_settings, load_settings)


class TestConfig:
    """Test cases for configuration management."""

    def test_llm_provider_details(self) -> None:
        """Test LLMProviderDetails model initialization."""
        provider = LLMProviderDetails(api_base="https://test.api.com")
        assert provider.api_base == "https://test.api.com"
        # Test with None value
        provider = LLMProviderDetails()
        assert provider.api_base is None

    def test_llm_concurrency_limit_default(self):
        """Should default to 5 if not set in config or env."""
        settings = Settings()
        assert settings.llm_concurrency_limit == 5

    @patch.dict(os.environ, {"LLM_CONCURRENCY_LIMIT": "11"}, clear=True)
    def test_llm_concurrency_limit_env_override(self):
        """Should override with env variable."""
        settings = Settings()
        assert settings.llm_concurrency_limit == 11

    def test_llm_concurrency_limit_from_yaml(self):
        """Should load from YAML config if present."""
        yaml_content = {"llm_concurrency_limit": 7}
        with patch("builtins.open", mock_open(read_data=yaml.dump(yaml_content))):
            with patch("os.path.exists", return_value=True):
                settings = load_settings()
                assert settings.llm_concurrency_limit == 7

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "sqlite:///test.db",
            "LOG_LEVEL": "DEBUG",
            "OPENAI_API_KEY": "test_openai_key",
        },
        clear=True,
    )
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_settings_from_env_only(
        self,
        mock_file_open: MagicMock,
        mock_os_path_exists: MagicMock,
    ) -> None:
        """Test loading settings from environment variables only."""
        # Mock that config.yml doesn't exist
        mock_os_path_exists.return_value = False

        # Call the function
        settings = load_settings()

        # Verify settings loaded from environment
        assert (
            settings.database_url == "sqlite+aiosqlite:///test.db"
        )  # Note the driver replacement
        assert settings.log_level == "DEBUG"
        assert settings.openai_api_key == "test_openai_key"

        # Verify defaults for YAML settings (those not set by ENV)
        assert settings.default_provider == "openrouter"
        assert settings.default_spell_check_language == "sv_SE"
        assert settings.supported_spell_check_languages == ["sv_SE", "en_US", "en_GB"]

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "sqlite:///test.db",
        },
        clear=True,
    )
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_settings_with_yaml(
        self,
        mock_file_open: MagicMock,
        mock_os_path_exists: MagicMock,
    ) -> None:
        """Test loading settings from both environment and YAML."""
        # Mock that config.yml exists
        mock_os_path_exists.return_value = True

        # Create yaml content with proper LLM provider details
        yaml_content = {
            "default_provider": "openai",
            "temperature": 0.5,
            "max_tokens_response": 500,
            "system_prompt": "Test prompt",
            "llm_providers": {"openai": {"api_base": "https://test.openai.com"}},
            "default_spell_check_language": "en_US",
            "supported_spell_check_languages": ["en_US"],
        }

        # Mock yaml loading
        mock_file_open.return_value.read.return_value = yaml.dump(yaml_content)

        # Call the function
        with patch("yaml.safe_load", return_value=yaml_content):
            settings = load_settings()

        # Verify settings loaded from environment
        assert settings.database_url == "sqlite+aiosqlite:///test.db"

        # Verify settings loaded from YAML
        assert settings.default_provider == "openai"
        assert settings.temperature == 0.5
        assert settings.max_tokens_response == 500
        assert settings.system_prompt == "Test prompt"

        # Check if llm_providers dictionary is correctly set
        assert "openai" in settings.llm_providers
        # The provider_details is now a Pydantic model
        assert settings.llm_providers["openai"].api_base == "https://test.openai.com"
        # Ensure default values are set for other fields
        assert settings.llm_providers["openai"].max_tokens == 1024
        assert settings.llm_providers["openai"].temperature == 0.7

        assert settings.default_spell_check_language == "en_US"
        assert settings.supported_spell_check_languages == ["en_US"]

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "sqlite:///test.db",
            "DEFAULT_PROVIDER": "anthropic",
            "DEFAULT_SPELL_CHECK_LANGUAGE": "en_GB",
        },
        clear=True,
    )
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_env_overrides_yaml(
        self,
        mock_file_open: MagicMock,
        mock_os_path_exists: MagicMock,
    ) -> None:
        """Test that environment variables override YAML settings."""
        # Mock that config.yml exists
        mock_os_path_exists.return_value = True

        # Create yaml content
        yaml_content = {
            "default_provider": "openai",
            "temperature": 0.5,
            "default_spell_check_language": "sv_SE",
            "supported_spell_check_languages": ["sv_SE", "en_US"],
        }

        # Mock yaml loading
        mock_file_open.return_value.read.return_value = yaml.dump(yaml_content)

        with patch("yaml.safe_load", return_value=yaml_content):
            settings = load_settings()

        # Environment should override YAML
        assert settings.default_provider == "anthropic"
        assert settings.temperature == 0.5
        assert settings.default_spell_check_language == "en_GB"
        assert settings.supported_spell_check_languages == ["sv_SE", "en_US"]

    def test_sqlite_driver_replacement(self) -> None:
        """Test that SQLite URLs have their driver replaced for async support."""
        # Create settings with SQLite URL
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"}, clear=True):
            settings = load_settings()

        # Check URL transformation
        assert settings.database_url == "sqlite+aiosqlite:///test.db"

        # Test no replacement for non-SQLite URLs
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost/db"},
            clear=True,
        ):
            settings = load_settings()
        assert settings.database_url == "postgresql://user:pass@localhost/db"

        # Test already async SQLite URL
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite+aiosqlite:///another.db"},
            clear=True,
        ):
            settings = load_settings()
        assert settings.database_url == "sqlite+aiosqlite:///another.db"

    def test_essay_input_path_property(self, tmp_path: Path) -> None:
        """Test the essay_input_path property creates the directory."""
        input_dir_name = "test_essay_input"
        test_input_dir = tmp_path / input_dir_name

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(essay_input_dir=str(test_input_dir))

        # Access the property
        path = settings.essay_input_path
        assert path == test_input_dir
        assert test_input_dir.exists()
        assert test_input_dir.is_dir()

    def test_cache_directory_path_property(self, tmp_path: Path) -> None:
        """Test the cache_directory_path property creates the directory."""
        cache_dir_name = "test_cache_dir"
        test_cache_dir = tmp_path / cache_dir_name

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(cache_directory=str(test_cache_dir))

        # Access the property
        path = settings.cache_directory_path
        assert path == test_cache_dir
        assert test_cache_dir.exists()
        assert test_cache_dir.is_dir()

    @patch("src.cj_essay_assessment.config.load_settings")
    def test_get_settings_creates_new_instance(self, mock_load: MagicMock) -> None:
        """Test that get_settings returns a fresh settings instance each time."""
        # Setup mock to return a new Settings object each time
        mock_load.side_effect = lambda: Settings()

        # Get settings twice
        s1 = get_settings()
        s2 = get_settings()

        # Verify different instances were returned (not a singleton)
        assert s1 is not s2
        # Verify load_settings was called each time
        assert mock_load.call_count == 2
