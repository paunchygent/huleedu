"""
Unit tests for File Service validation configuration.

Tests the enhanced configuration settings for content validation
to ensure proper defaults, environment variable handling, and validation rules.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from common_core.enums import ProcessingEvent, topic_name
from services.file_service.config import Settings as ValidationSettings


class TestValidationSettings:
    """Test suite for validation configuration settings."""

    def test_default_validation_settings(self) -> None:
        """Test that validation settings have correct default values."""
        settings = ValidationSettings()

        # Test validation feature defaults
        assert settings.CONTENT_VALIDATION_ENABLED is True
        assert settings.MIN_CONTENT_LENGTH == 50
        assert settings.MAX_CONTENT_LENGTH == 50000
        assert settings.VALIDATION_LOG_LEVEL == "INFO"

        # Test that original settings are preserved
        assert settings.LOG_LEVEL == "INFO"
        assert settings.SERVICE_NAME == "file-service"
        assert settings.HTTP_PORT == 7001

    def test_validation_enabled_toggle(self) -> None:
        """Test that validation can be disabled via configuration."""
        with patch.dict(os.environ, {"FILE_SERVICE_CONTENT_VALIDATION_ENABLED": "false"}):
            settings = ValidationSettings()
            assert settings.CONTENT_VALIDATION_ENABLED is False

    def test_custom_length_limits_from_env(self) -> None:
        """Test that custom length limits can be set via environment variables."""
        env_vars = {
            "FILE_SERVICE_MIN_CONTENT_LENGTH": "25",
            "FILE_SERVICE_MAX_CONTENT_LENGTH": "2000",
        }

        with patch.dict(os.environ, env_vars):
            settings = ValidationSettings()
            assert settings.MIN_CONTENT_LENGTH == 25
            assert settings.MAX_CONTENT_LENGTH == 2000

    def test_validation_log_level_from_env(self) -> None:
        """Test that validation log level can be configured separately."""
        with patch.dict(os.environ, {"FILE_SERVICE_VALIDATION_LOG_LEVEL": "DEBUG"}):
            settings = ValidationSettings()
            assert settings.VALIDATION_LOG_LEVEL == "DEBUG"
            # Ensure main log level is unchanged
            assert settings.LOG_LEVEL == "INFO"

    def test_kafka_topic_configuration(self) -> None:
        """Test that Kafka topics are properly configured for validation events."""
        settings = ValidationSettings()

        # Test existing topic is preserved
        assert topic_name(
            ProcessingEvent.ESSAY_CONTENT_PROVISIONED,
        ) == settings.ESSAY_CONTENT_PROVISIONED_TOPIC

        # Test new validation failure topic is configured
        assert settings.ESSAY_VALIDATION_FAILED_TOPIC == "huleedu.file.essay.validation.failed.v1"

    def test_env_prefix_handling(self) -> None:
        """Test that environment variables use correct FILE_SERVICE_ prefix."""
        env_vars = {
            "FILE_SERVICE_MIN_CONTENT_LENGTH": "100",
            "MIN_CONTENT_LENGTH": "200",  # Should be ignored due to prefix
        }

        with patch.dict(os.environ, env_vars):
            settings = ValidationSettings()
            # Should use the prefixed version
            assert settings.MIN_CONTENT_LENGTH == 100

    def test_invalid_boolean_env_var_handling(self) -> None:
        """Test handling of invalid boolean values in environment variables."""
        with patch.dict(os.environ, {"FILE_SERVICE_CONTENT_VALIDATION_ENABLED": "invalid"}):
            with pytest.raises(ValueError):
                ValidationSettings()

    def test_invalid_integer_env_var_handling(self) -> None:
        """Test handling of invalid integer values in environment variables."""
        with patch.dict(os.environ, {"FILE_SERVICE_MIN_CONTENT_LENGTH": "not_a_number"}):
            with pytest.raises(ValueError):
                ValidationSettings()

    def test_negative_length_values(self) -> None:
        """Test handling of negative length values in configuration."""
        env_vars = {
            "FILE_SERVICE_MIN_CONTENT_LENGTH": "-10",
            "FILE_SERVICE_MAX_CONTENT_LENGTH": "-100",
        }

        with patch.dict(os.environ, env_vars):
            settings = ValidationSettings()
            # Pydantic allows negative values - business logic should validate
            assert settings.MIN_CONTENT_LENGTH == -10
            assert settings.MAX_CONTENT_LENGTH == -100

    def test_length_limit_boundary_values(self) -> None:
        """Test configuration with boundary values for length limits."""
        env_vars = {
            "FILE_SERVICE_MIN_CONTENT_LENGTH": "1",
            "FILE_SERVICE_MAX_CONTENT_LENGTH": "1000000",
        }

        with patch.dict(os.environ, env_vars):
            settings = ValidationSettings()
            assert settings.MIN_CONTENT_LENGTH == 1
            assert settings.MAX_CONTENT_LENGTH == 1000000

    def test_model_config_preservation(self) -> None:
        """Test that model configuration is properly set for environment handling."""
        settings = ValidationSettings()

        # Verify model config is set correctly
        config = settings.model_config
        assert config["env_file"] == ".env"
        assert config["env_file_encoding"] == "utf-8"
        assert config["extra"] == "ignore"
        assert config["env_prefix"] == "FILE_SERVICE_"

    def test_settings_serialization(self) -> None:
        """Test that settings can be serialized properly for logging/debugging."""
        settings = ValidationSettings()

        # Test that settings can be converted to dict
        settings_dict = settings.model_dump()

        assert "CONTENT_VALIDATION_ENABLED" in settings_dict
        assert "MIN_CONTENT_LENGTH" in settings_dict
        assert "MAX_CONTENT_LENGTH" in settings_dict
        assert settings_dict["CONTENT_VALIDATION_ENABLED"] is True
        assert settings_dict["MIN_CONTENT_LENGTH"] == 50

    def test_settings_validation_consistency(self) -> None:
        """Test that settings maintain consistency between related values."""
        settings = ValidationSettings()

        # Test that max length is greater than min length with defaults
        assert settings.MAX_CONTENT_LENGTH > settings.MIN_CONTENT_LENGTH

        # Test service name consistency
        assert settings.SERVICE_NAME == "file-service"
        assert "FILE_SERVICE_" in settings.model_config["env_prefix"]

    def test_multiple_env_var_combinations(self) -> None:
        """Test various combinations of environment variable settings."""
        test_combinations = [
            {
                "FILE_SERVICE_CONTENT_VALIDATION_ENABLED": "true",
                "FILE_SERVICE_MIN_CONTENT_LENGTH": "30",
                "FILE_SERVICE_MAX_CONTENT_LENGTH": "5000",
                "FILE_SERVICE_VALIDATION_LOG_LEVEL": "WARNING",
            },
            {
                "FILE_SERVICE_CONTENT_VALIDATION_ENABLED": "false",
                "FILE_SERVICE_MIN_CONTENT_LENGTH": "0",
                "FILE_SERVICE_MAX_CONTENT_LENGTH": "100000",
            },
        ]

        for env_vars in test_combinations:
            with patch.dict(os.environ, env_vars):
                settings = ValidationSettings()

                # Verify each setting is applied correctly
                assert (
                    env_vars.get("FILE_SERVICE_CONTENT_VALIDATION_ENABLED") == "true"
                ) == settings.CONTENT_VALIDATION_ENABLED
                assert int(
                    env_vars["FILE_SERVICE_MIN_CONTENT_LENGTH"],
                ) == settings.MIN_CONTENT_LENGTH
                assert int(
                    env_vars["FILE_SERVICE_MAX_CONTENT_LENGTH"],
                ) == settings.MAX_CONTENT_LENGTH

                if "FILE_SERVICE_VALIDATION_LOG_LEVEL" in env_vars:
                    assert (
                        env_vars["FILE_SERVICE_VALIDATION_LOG_LEVEL"]
                        == settings.VALIDATION_LOG_LEVEL
                    )
