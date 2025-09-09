"""
Unit tests for language tool service configuration validation.

Tests the Settings class for environment variable handling, Java configuration,
LanguageTool settings, default values, validation errors, and edge cases
following Rule 075 methodology for behavioral testing.
"""

from __future__ import annotations

import pytest
from common_core.config_enums import Environment
from pydantic import ValidationError

from services.language_tool_service.config import Settings


class TestLanguageToolServiceSettings:
    """Tests for language tool service configuration validation."""

    def test_settings_loads_default_values(self) -> None:
        """Test that Settings loads correct default values when no environment variables are set."""
        # Create settings instance with defaults (no environment overrides)
        settings = Settings()

        # Test core service defaults
        assert settings.SERVICE_NAME == "language-tool-service"
        assert settings.HTTP_PORT == 8085
        assert settings.HOST == "0.0.0.0"
        assert settings.LOG_LEVEL == "INFO"
        assert settings.ENVIRONMENT == Environment.DEVELOPMENT

        # Test LanguageTool API defaults
        assert settings.LANGUAGE_TOOL_TIMEOUT_SECONDS == 30
        assert settings.LANGUAGE_TOOL_MAX_RETRIES == 3

        # Test LanguageTool server defaults
        assert settings.LANGUAGE_TOOL_PORT == 8081
        assert settings.LANGUAGE_TOOL_HEAP_SIZE == "512m"
        assert settings.LANGUAGE_TOOL_JAR_PATH == "/app/languagetool/languagetool-server.jar"
        assert settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS == 10
        assert settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS == 30
        assert settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL == 30

        # Test category filtering defaults
        expected_allowed = [
            "GRAMMAR",
            "CONFUSED_WORDS",
            "AGREEMENT",
            "PUNCTUATION",
            "REDUNDANCY",
            "STYLE",
        ]
        expected_blocked = ["TYPOS", "MISSPELLING", "SPELLING", "TYPOGRAPHY"]
        assert settings.GRAMMAR_CATEGORIES_ALLOWED == expected_allowed
        assert settings.GRAMMAR_CATEGORIES_BLOCKED == expected_blocked

    @pytest.mark.parametrize(
        "env_var, value, field_name, expected",
        [
            (
                "LANGUAGE_TOOL_SERVICE_SERVICE_NAME",
                "custom_language_tool",
                "SERVICE_NAME",
                "custom_language_tool",
            ),
            ("LANGUAGE_TOOL_SERVICE_HTTP_PORT", "8090", "HTTP_PORT", 8090),
            ("LANGUAGE_TOOL_SERVICE_HOST", "127.0.0.1", "HOST", "127.0.0.1"),
            ("LANGUAGE_TOOL_SERVICE_LOG_LEVEL", "DEBUG", "LOG_LEVEL", "DEBUG"),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS",
                "60",
                "LANGUAGE_TOOL_TIMEOUT_SECONDS",
                60,
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_RETRIES",
                "5",
                "LANGUAGE_TOOL_MAX_RETRIES",
                5,
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT",
                "8082",
                "LANGUAGE_TOOL_PORT",
                8082,
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE",
                "1024m",
                "LANGUAGE_TOOL_HEAP_SIZE",
                "1024m",
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH",
                "/custom/path/languagetool.jar",
                "LANGUAGE_TOOL_JAR_PATH",
                "/custom/path/languagetool.jar",
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS",
                "20",
                "LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS",
                20,
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS",
                "45",
                "LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS",
                45,
            ),
            (
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL",
                "60",
                "LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL",
                60,
            ),
        ],
    )
    def test_environment_variable_loading_with_prefix(
        self,
        env_var: str,
        value: str,
        field_name: str,
        expected: str | int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that environment variables are loaded correctly with LANGUAGE_TOOL_SERVICE_ prefix."""
        monkeypatch.setenv(env_var, value)
        settings = Settings()
        actual_value = getattr(settings, field_name)
        assert actual_value == expected

    @pytest.mark.parametrize(
        "env_value, expected_enum",
        [
            ("development", Environment.DEVELOPMENT),
            ("staging", Environment.STAGING),
            ("production", Environment.PRODUCTION),
            ("testing", Environment.TESTING),
        ],
    )
    def test_environment_enum_conversion(
        self, env_value: str, expected_enum: Environment, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that ENVIRONMENT string values are correctly converted to Environment enum."""
        monkeypatch.setenv("ENVIRONMENT", env_value)
        settings = Settings()
        assert settings.ENVIRONMENT == expected_enum
        assert isinstance(settings.ENVIRONMENT, Environment)

    @pytest.mark.parametrize(
        "env_var, invalid_value",
        [
            ("LANGUAGE_TOOL_SERVICE_HTTP_PORT", "not_a_port"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS", "invalid_timeout"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_RETRIES", "retry_text"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT", "port_text"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS", "request_text"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS", "timeout_text"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL", "interval_text"),
        ],
    )
    def test_invalid_integer_environment_variables_raise_validation_error(
        self, env_var: str, invalid_value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid integer values in environment variables raise ValidationError."""
        monkeypatch.setenv(env_var, invalid_value)
        with pytest.raises(ValidationError) as exc_info:
            Settings()

        # Verify the error is about type validation
        error_message = str(exc_info.value)
        # Extract field name from environment variable (remove prefix)
        field_name = env_var.replace("LANGUAGE_TOOL_SERVICE_", "")
        assert field_name in error_message

    def test_invalid_environment_enum_value_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid Environment enum values raise ValidationError."""
        monkeypatch.setenv("ENVIRONMENT", "invalid_environment")
        with pytest.raises(ValidationError) as exc_info:
            Settings()

        # Verify the error is about enum validation
        assert "ENVIRONMENT" in str(exc_info.value)

    @pytest.mark.parametrize(
        "port_field, env_var, invalid_port",
        [
            ("HTTP_PORT", "LANGUAGE_TOOL_SERVICE_HTTP_PORT", "-1"),
            ("HTTP_PORT", "LANGUAGE_TOOL_SERVICE_HTTP_PORT", "0"),
            ("HTTP_PORT", "LANGUAGE_TOOL_SERVICE_HTTP_PORT", "65536"),
            ("LANGUAGE_TOOL_PORT", "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT", "-5"),
            ("LANGUAGE_TOOL_PORT", "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT", "999999"),
        ],
    )
    def test_invalid_port_numbers_edge_cases(
        self, port_field: str, env_var: str, invalid_port: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid port numbers (out of valid range) are handled gracefully."""
        monkeypatch.setenv(env_var, invalid_port)
        # Note: Pydantic doesn't enforce port range validation by default,
        # so these values will be accepted as integers but may cause runtime issues
        settings = Settings()
        port_value = getattr(settings, port_field)
        assert isinstance(port_value, int)
        assert port_value == int(invalid_port)

    @pytest.mark.parametrize(
        "heap_size_value",
        [
            "256m",
            "512m",
            "1g",
            "2048m",
            "4g",
            "1024M",
            "2G",
        ],
    )
    def test_heap_size_format_variations(
        self, heap_size_value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that various heap size format variations are accepted."""
        env_var = "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE"

        monkeypatch.setenv(env_var, heap_size_value)
        settings = Settings()
        assert settings.LANGUAGE_TOOL_HEAP_SIZE == heap_size_value

    @pytest.mark.parametrize(
        "jar_path",
        [
            "/app/languagetool/languagetool-server.jar",
            "/custom/path/languagetool.jar",
            "/opt/languagetool/server.jar",
            "/tmp/languagetool-standalone-6.3.jar",
            "C:\\Program Files\\LanguageTool\\languagetool.jar",  # Windows path
        ],
    )
    def test_jar_path_variations(self, jar_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that various JAR path formats are accepted."""
        env_var = "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH"

        monkeypatch.setenv(env_var, jar_path)
        settings = Settings()
        assert settings.LANGUAGE_TOOL_JAR_PATH == jar_path

    @pytest.mark.parametrize(
        "field_name, env_var, custom_json, expected_list",
        [
            (
                "GRAMMAR_CATEGORIES_ALLOWED",
                "LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED",
                '["GRAMMAR", "STYLE"]',
                ["GRAMMAR", "STYLE"],
            ),
            (
                "GRAMMAR_CATEGORIES_BLOCKED",
                "LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_BLOCKED",
                '["TYPOS", "MISSPELLING"]',
                ["TYPOS", "MISSPELLING"],
            ),
            (
                "GRAMMAR_CATEGORIES_ALLOWED",
                "LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED",
                '["CUSTOM_CATEGORY_ÅÄÖ"]',  # Swedish characters
                ["CUSTOM_CATEGORY_ÅÄÖ"],
            ),
        ],
    )
    def test_grammar_categories_list_environment_variable_override(
        self,
        field_name: str,
        env_var: str,
        custom_json: str,
        expected_list: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that grammar category lists can be overridden via JSON environment variables."""
        # Pydantic automatically parses JSON string format for list fields
        monkeypatch.setenv(env_var, custom_json)
        settings = Settings()
        actual_value = getattr(settings, field_name)
        assert actual_value == expected_list

    @pytest.mark.parametrize(
        "timeout_field, env_var, zero_value, large_value",
        [
            (
                "LANGUAGE_TOOL_TIMEOUT_SECONDS",
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS",
                "0",
                "3600",
            ),
            (
                "LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS",
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS",
                "0",
                "300",
            ),
            (
                "LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL",
                "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL",
                "0",
                "3600",
            ),
        ],
    )
    def test_timeout_field_boundary_values(
        self,
        timeout_field: str,
        env_var: str,
        zero_value: str,
        large_value: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test timeout fields with boundary values (zero and large numbers)."""
        # Test zero value
        monkeypatch.setenv(env_var, zero_value)
        settings = Settings()
        assert getattr(settings, timeout_field) == 0

        # Test large value
        monkeypatch.setenv(env_var, large_value)
        settings = Settings()
        assert getattr(settings, timeout_field) == int(large_value)

    @pytest.mark.parametrize(
        "field_name, swedish_value",
        [
            ("SERVICE_NAME", "språkverktyg-tjänst-åäö"),
            ("HOST", "språkserver-malmö.example.com"),
            ("LOG_LEVEL", "FELSÖKNING"),  # Swedish for DEBUG
            ("LANGUAGE_TOOL_JAR_PATH", "/app/språkverktyg/språkverktyg-åäö.jar"),
            ("LANGUAGE_TOOL_HEAP_SIZE", "1024m"),  # No Swedish characters expected
        ],
    )
    def test_swedish_characters_in_configuration_values(
        self, field_name: str, swedish_value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that Swedish characters åäöÅÄÖ are properly handled in configuration values."""
        env_var = f"LANGUAGE_TOOL_SERVICE_{field_name}"

        monkeypatch.setenv(env_var, swedish_value)
        settings = Settings()
        actual_value = getattr(settings, field_name)
        assert actual_value == swedish_value

    def test_environment_variable_prefix_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that only LANGUAGE_TOOL_SERVICE_ prefixed environment variables are used."""
        env_vars = {
            "LANGUAGE_TOOL_SERVICE_SERVICE_NAME": "correct_language_tool_service",
            "SERVICE_NAME": "wrong_service_name",  # Should be ignored
            "LANGUAGE_TOOL_SERVICE_LOG_LEVEL": "DEBUG",
            "LOG_LEVEL": "ERROR",  # Should be ignored
            "LANGUAGE_TOOL_SERVICE_HTTP_PORT": "8090",
            "HTTP_PORT": "9999",  # Should be ignored
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        settings = Settings()

        # Should use the LANGUAGE_TOOL_SERVICE_ prefixed versions
        assert settings.SERVICE_NAME == "correct_language_tool_service"
        assert settings.LOG_LEVEL == "DEBUG"
        assert settings.HTTP_PORT == 8090

    def test_settings_extra_ignore_behavior(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that extra environment variables are ignored due to model_config extra='ignore'."""
        env_vars = {
            "LANGUAGE_TOOL_SERVICE_UNKNOWN_FIELD": "should_be_ignored",
            "LANGUAGE_TOOL_SERVICE_FAKE_JAVA_SETTING": "also_ignored",
            "LANGUAGE_TOOL_SERVICE_SERVICE_NAME": "valid_service_name",
            "LANGUAGE_TOOL_SERVICE_NONEXISTENT_CONFIG": "ignored_value",
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        # Should not raise an error due to extra='ignore'
        settings = Settings()
        assert settings.SERVICE_NAME == "valid_service_name"

        # Unknown fields should not be accessible
        assert not hasattr(settings, "UNKNOWN_FIELD")
        assert not hasattr(settings, "FAKE_JAVA_SETTING")
        assert not hasattr(settings, "NONEXISTENT_CONFIG")

    def test_zero_value_integer_environment_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test handling of zero values for integer environment variables."""
        env_vars = {
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS": "0",
            "LANGUAGE_TOOL_SERVICE_HTTP_PORT": "0",
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_RETRIES": "0",
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        settings = Settings()
        assert settings.LANGUAGE_TOOL_TIMEOUT_SECONDS == 0
        assert settings.HTTP_PORT == 0
        assert settings.LANGUAGE_TOOL_MAX_RETRIES == 0
        assert isinstance(settings.LANGUAGE_TOOL_TIMEOUT_SECONDS, int)
        assert isinstance(settings.HTTP_PORT, int)
        assert isinstance(settings.LANGUAGE_TOOL_MAX_RETRIES, int)

    @pytest.mark.parametrize(
        "field_name, large_value",
        [
            ("LANGUAGE_TOOL_TIMEOUT_SECONDS", 2147483647),
            ("HTTP_PORT", 65535),  # Max port number
            ("LANGUAGE_TOOL_PORT", 65535),
            ("LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS", 1000),
            ("LANGUAGE_TOOL_MAX_RETRIES", 999),
        ],
    )
    def test_very_large_integer_environment_variables(
        self, field_name: str, large_value: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test handling of very large integer values."""
        env_var = f"LANGUAGE_TOOL_SERVICE_{field_name}"

        monkeypatch.setenv(env_var, str(large_value))
        settings = Settings()
        actual_value = getattr(settings, field_name)
        assert actual_value == large_value

    def test_edge_case_empty_string_environment_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test handling of empty string environment variables."""
        env_vars = {
            "LANGUAGE_TOOL_SERVICE_SERVICE_NAME": "",
            "LANGUAGE_TOOL_SERVICE_HOST": "",
            "LANGUAGE_TOOL_SERVICE_LOG_LEVEL": "",
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH": "",
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE": "",
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        settings = Settings()

        # Empty strings should be treated as valid values
        assert settings.SERVICE_NAME == ""
        assert settings.HOST == ""
        assert settings.LOG_LEVEL == ""
        assert settings.LANGUAGE_TOOL_JAR_PATH == ""
        assert settings.LANGUAGE_TOOL_HEAP_SIZE == ""

    @pytest.mark.parametrize(
        "env_value, is_dev, is_staging, is_prod, is_testing, requires_security",
        [
            ("development", True, False, False, False, False),
            ("staging", False, True, False, False, True),
            ("production", False, False, True, False, True),
            ("testing", False, False, False, True, False),
        ],
    )
    def test_environment_methods_behavior(
        self,
        env_value: str,
        is_dev: bool,
        is_staging: bool,
        is_prod: bool,
        is_testing: bool,
        requires_security: bool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that environment detection methods work correctly."""
        monkeypatch.setenv("ENVIRONMENT", env_value)
        settings = Settings()
        assert settings.is_development() == is_dev
        assert settings.is_staging() == is_staging
        assert settings.is_production() == is_prod
        assert settings.is_testing() == is_testing
        assert settings.requires_security() == requires_security

    def test_secrets_are_properly_masked_in_string_representation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that sensitive fields are properly masked in string representation."""
        env_vars = {
            "HULEEDU_DB_PASSWORD": "super_secret_db_password_åäö",
            "HULEEDU_INTERNAL_API_KEY": "secret_api_key_ÅÄÖ",
            "ENVIRONMENT": "development",
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        settings = Settings()
        settings_str = str(settings)

        # Secrets should be properly masked
        assert "super_secret_db_password_åäö" not in settings_str
        assert "secret_api_key_ÅÄÖ" not in settings_str
        assert "***MASKED***" in settings_str

        # Non-sensitive values should be present
        assert "language-tool-service" in settings_str
        assert "development" in settings_str

    def test_repr_properly_masks_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that repr() properly masks sensitive information."""
        env_vars = {
            "HULEEDU_DB_PASSWORD": "secret_in_repr_åäö",
            "HULEEDU_INTERNAL_API_KEY": "api_key_in_repr_ÅÄÖ",
            "ENVIRONMENT": "development",
        }

        for env_var, value in env_vars.items():
            monkeypatch.setenv(env_var, value)

        settings = Settings()
        settings_repr = repr(settings)

        # Secrets should be properly masked in repr
        assert "secret_in_repr_åäö" not in settings_repr
        assert "api_key_in_repr_ÅÄÖ" not in settings_repr
        assert "***MASKED***" in settings_repr

        # Verify repr and str provide the same secure representation
        assert repr(settings) == str(settings)

    def test_concurrent_request_limits_validation(self) -> None:
        """Test that concurrent request limits are properly handled."""
        test_cases = [
            1,  # Minimum reasonable value
            10,  # Default value
            100,  # High load value
            1000,  # Very high load
        ]

        for expected in test_cases:
            # Test each case with direct field override
            settings = Settings(LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS=expected)
            assert settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS == expected

    def test_configuration_field_types_are_correct(self) -> None:
        """Test that all configuration fields have the correct Python types."""
        # Create settings with defaults (no environment overrides)
        settings = Settings()

        # String fields
        assert isinstance(settings.SERVICE_NAME, str)
        assert isinstance(settings.HOST, str)
        assert isinstance(settings.LOG_LEVEL, str)
        assert isinstance(settings.LANGUAGE_TOOL_HEAP_SIZE, str)
        assert isinstance(settings.LANGUAGE_TOOL_JAR_PATH, str)

        # Integer fields
        assert isinstance(settings.HTTP_PORT, int)
        assert isinstance(settings.LANGUAGE_TOOL_TIMEOUT_SECONDS, int)
        assert isinstance(settings.LANGUAGE_TOOL_MAX_RETRIES, int)
        assert isinstance(settings.LANGUAGE_TOOL_PORT, int)
        assert isinstance(settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS, int)
        assert isinstance(settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS, int)
        assert isinstance(settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL, int)

        # List fields
        assert isinstance(settings.GRAMMAR_CATEGORIES_ALLOWED, list)
        assert isinstance(settings.GRAMMAR_CATEGORIES_BLOCKED, list)
        assert all(isinstance(category, str) for category in settings.GRAMMAR_CATEGORIES_ALLOWED)
        assert all(isinstance(category, str) for category in settings.GRAMMAR_CATEGORIES_BLOCKED)

        # Enum field
        assert isinstance(settings.ENVIRONMENT, Environment)

    def test_model_config_settings_are_correct(self) -> None:
        """Test that model configuration settings are properly set."""
        settings = Settings()

        # Verify the model config is applied correctly
        assert settings.model_config["env_file"] == ".env"
        assert settings.model_config["env_file_encoding"] == "utf-8"
        assert settings.model_config["extra"] == "ignore"
        assert settings.model_config["env_prefix"] == "LANGUAGE_TOOL_SERVICE_"
