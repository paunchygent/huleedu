"""
Unit tests for entitlements service configuration validation.

Tests the Settings class for environment variable handling, database URL generation,
default values, secret masking, validation errors, and Swedish character handling
following Rule 075 methodology for behavioral testing.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from common_core.config_enums import Environment
from pydantic import ValidationError

from services.entitlements_service.config import Settings


class TestEntitlementsServiceSettings:
    """Tests for entitlements service configuration validation."""

    def test_settings_loads_default_values(self) -> None:
        """Test that Settings loads correct default values when no environment variables are set."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            # Test key service defaults
            assert settings.SERVICE_NAME == "entitlements_service"
            assert settings.USE_MOCK_REPOSITORY is False
            assert settings.DEFAULT_USER_CREDITS == 50
            assert settings.DEFAULT_ORG_CREDITS == 500
            assert settings.POLICY_FILE == "policies/default.yaml"
            assert settings.POLICY_CACHE_TTL == 300
            assert settings.RATE_LIMIT_ENABLED is True
            assert settings.REDIS_URL == "redis://redis:6379/0"
            assert settings.KAFKA_BOOTSTRAP_SERVERS == "kafka:9092"
            assert settings.METRICS_PORT == 8083
            assert settings.LOG_LEVEL == "INFO"
            assert settings.ENVIRONMENT == Environment.DEVELOPMENT

    @pytest.mark.parametrize(
        "env_var, value, field_name, expected",
        [
            (
                "ENTITLEMENTS_SERVICE_NAME",
                "custom_entitlements",
                "SERVICE_NAME",
                "custom_entitlements",
            ),
            ("ENTITLEMENTS_USE_MOCK_REPOSITORY", "true", "USE_MOCK_REPOSITORY", True),
            (
                "ENTITLEMENTS_POLICY_FILE",
                "policies/custom.yaml",
                "POLICY_FILE",
                "policies/custom.yaml",
            ),
            ("ENTITLEMENTS_POLICY_CACHE_TTL", "600", "POLICY_CACHE_TTL", 600),
            ("ENTITLEMENTS_DEFAULT_USER_CREDITS", "100", "DEFAULT_USER_CREDITS", 100),
            ("ENTITLEMENTS_METRICS_PORT", "9090", "METRICS_PORT", 9090),
            ("ENTITLEMENTS_DATABASE_POOL_SIZE", "10", "DATABASE_POOL_SIZE", 10),
            (
                "ENTITLEMENTS_REDIS_URL",
                "redis://custom:6380/1",
                "REDIS_URL",
                "redis://custom:6380/1",
            ),
            (
                "ENTITLEMENTS_KAFKA_BOOTSTRAP_SERVERS",
                "broker1:9092,broker2:9092",
                "KAFKA_BOOTSTRAP_SERVERS",
                "broker1:9092,broker2:9092",
            ),
            (
                "ENTITLEMENTS_PRODUCER_CLIENT_ID",
                "custom-producer-id",
                "PRODUCER_CLIENT_ID",
                "custom-producer-id",
            ),
            ("ENTITLEMENTS_LOG_LEVEL", "DEBUG", "LOG_LEVEL", "DEBUG"),
        ],
    )
    def test_environment_variable_loading_with_prefix(
        self, env_var: str, value: str, field_name: str, expected: str | int | bool
    ) -> None:
        """Test that environment variables are loaded correctly with ENTITLEMENTS_ prefix."""
        with patch.dict(os.environ, {env_var: value}):
            settings = Settings()
            actual_value = getattr(settings, field_name)

            # Handle SecretStr fields by comparing secret values
            if hasattr(actual_value, "get_secret_value"):
                assert actual_value.get_secret_value() == expected
            else:
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
    def test_environment_enum_conversion(self, env_value: str, expected_enum: Environment) -> None:
        """Test that ENVIRONMENT string values are correctly converted to Environment enum."""
        with patch.dict(os.environ, {"ENVIRONMENT": env_value}):
            settings = Settings()
            assert settings.ENVIRONMENT == expected_enum
            assert isinstance(settings.ENVIRONMENT, Environment)

    @pytest.mark.parametrize(
        "env_var, invalid_value",
        [
            ("ENTITLEMENTS_POLICY_CACHE_TTL", "not_a_number"),
            ("ENTITLEMENTS_DEFAULT_USER_CREDITS", "text_value"),
            ("ENTITLEMENTS_METRICS_PORT", "port_text"),
            ("ENTITLEMENTS_DATABASE_POOL_SIZE", "pool_text"),
            ("ENTITLEMENTS_KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "failure_text"),
        ],
    )
    def test_invalid_integer_environment_variables_raise_validation_error(
        self, env_var: str, invalid_value: str
    ) -> None:
        """Test that invalid integer values in environment variables raise ValidationError."""
        with patch.dict(os.environ, {env_var: invalid_value}):
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            # Verify the error is about type validation
            error_message = str(exc_info.value)
            # Extract field name from environment variable (remove ENTITLEMENTS_ prefix)
            field_name = env_var.replace("ENTITLEMENTS_", "")
            assert field_name in error_message

    def test_invalid_environment_enum_value_raises_validation_error(self) -> None:
        """Test that invalid Environment enum values raise ValidationError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "invalid_environment"}):
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            # Verify the error is about enum validation
            assert "ENVIRONMENT" in str(exc_info.value)

    def test_database_url_development_environment(self) -> None:
        """Test database URL generation for development environment."""
        env_vars = {
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "test_user",
            "HULEEDU_DB_PASSWORD": "test_password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.DATABASE_URL

            expected_url = (
                "postgresql+asyncpg://test_user:test_password@localhost:5444/huleedu_entitlements"
            )
            assert database_url == expected_url

    def test_database_url_production_environment_with_all_variables(self) -> None:
        """Test database URL generation for production environment with all required variables."""
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "prod.entitlements.example.com",
            "HULEEDU_PROD_DB_PORT": "5433",
            "HULEEDU_PROD_DB_PASSWORD": "secure_prod_password",
            "HULEEDU_DB_USER": "prod_user",
            "HULEEDU_DB_PASSWORD": "dev_password",  # Should be ignored in production
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.DATABASE_URL

            expected_url = "postgresql+asyncpg://prod_user:secure_prod_password@prod.entitlements.example.com:5433/huleedu_entitlements"
            assert database_url == expected_url

    def test_database_url_production_environment_with_default_port(self) -> None:
        """Test production environment uses default port 5432 when port is not specified."""
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "prod.entitlements.example.com",
            "HULEEDU_PROD_DB_PASSWORD": "secure_prod_password",
            "HULEEDU_DB_USER": "prod_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.DATABASE_URL

            expected_url = "postgresql+asyncpg://prod_user:secure_prod_password@prod.entitlements.example.com:5432/huleedu_entitlements"
            assert database_url == expected_url

    def test_database_url_service_specific_override(self) -> None:
        """Test that ENTITLEMENTS_SERVICE_DATABASE_URL overrides database URL generation."""
        override_url = "postgresql+asyncpg://override_user:override_pass@override.host:5555/override_entitlements"
        env_vars = {
            "ENTITLEMENTS_SERVICE_DATABASE_URL": override_url,
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "should_be_ignored.com",
            "HULEEDU_PROD_DB_PASSWORD": "should_be_ignored",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.DATABASE_URL == override_url

    def test_database_url_production_missing_host_raises_error(self) -> None:
        """Test that missing production database host raises ValueError."""
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_PASSWORD": "secure_password",
            "HULEEDU_DB_USER": "test_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            with pytest.raises(ValueError) as exc_info:
                _ = settings.DATABASE_URL

            error_message = str(exc_info.value)
            assert "Production environment requires" in error_message
            assert "HULEEDU_PROD_DB_HOST" in error_message
            assert "HULEEDU_PROD_DB_PASSWORD" in error_message

    def test_database_url_production_missing_password_raises_error(self) -> None:
        """Test that missing production database password raises ValueError."""
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "prod.host.com",
            "HULEEDU_DB_USER": "test_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            with pytest.raises(ValueError) as exc_info:
                _ = settings.DATABASE_URL

            error_message = str(exc_info.value)
            assert "Production environment requires" in error_message
            assert "HULEEDU_PROD_DB_HOST" in error_message
            assert "HULEEDU_PROD_DB_PASSWORD" in error_message

    def test_database_url_development_missing_user_raises_error(self) -> None:
        """Test that missing development database user raises ValueError."""
        env_vars = {
            "ENVIRONMENT": "development",
            "HULEEDU_DB_PASSWORD": "dev_password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            with pytest.raises(ValueError) as exc_info:
                _ = settings.DATABASE_URL

            error_message = str(exc_info.value)
            assert "HULEEDU_DB_USER" in error_message
            assert "HULEEDU_DB_PASSWORD" in error_message

    def test_database_url_development_missing_password_raises_error(self) -> None:
        """Test that missing development database password raises ValueError."""
        env_vars = {
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "dev_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            with pytest.raises(ValueError) as exc_info:
                _ = settings.DATABASE_URL

            error_message = str(exc_info.value)
            assert "HULEEDU_DB_USER" in error_message
            assert "HULEEDU_DB_PASSWORD" in error_message

    @pytest.mark.parametrize(
        "field_name, swedish_value",
        [
            ("SERVICE_NAME", "berättigande_tjänst_åäö"),
            ("POLICY_FILE", "policies/skola_malmö.yaml"),
            ("PRODUCER_CLIENT_ID", "berättigande-producent-göteborg"),
            ("REDIS_URL", "redis://redis-malmö:6379/0"),
            ("KAFKA_BOOTSTRAP_SERVERS", "kafka-stockholm:9092,kafka-göteborg:9093"),
            ("LOG_LEVEL", "FELSÖKNING"),  # Swedish for DEBUG
        ],
    )
    def test_swedish_characters_in_configuration_values(
        self, field_name: str, swedish_value: str
    ) -> None:
        """Test that Swedish characters åäöÅÄÖ are properly handled in configuration values."""
        env_var = f"ENTITLEMENTS_{field_name}"

        with patch.dict(os.environ, {env_var: swedish_value}):
            settings = Settings()
            actual_value = getattr(settings, field_name)
            assert actual_value == swedish_value

    def test_swedish_database_name_in_development_url(self) -> None:
        """Test Swedish characters in database configuration for development environment."""
        env_vars = {
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "användare_åäö",
            "HULEEDU_DB_PASSWORD": "lösenord_ÅÄÖ",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.DATABASE_URL

            # Password should be URL-encoded to handle special characters safely
            expected_url = "postgresql+asyncpg://användare_åäö:l%C3%B6senord_%C3%85%C3%84%C3%96@localhost:5444/huleedu_entitlements"
            assert database_url == expected_url

    def test_swedish_database_credentials_in_production_url(self) -> None:
        """Test Swedish characters in production database configuration."""
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "databas-stockholm.example.com",
            "HULEEDU_PROD_DB_PASSWORD": "säkert_lösenord_ÅÄÖ",
            "HULEEDU_DB_USER": "användare_malmö",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.DATABASE_URL

            # Password should be URL-encoded to handle special characters safely
            expected_url = "postgresql+asyncpg://användare_malmö:s%C3%A4kert_l%C3%B6senord_%C3%85%C3%84%C3%96@databas-stockholm.example.com:5432/huleedu_entitlements"
            assert database_url == expected_url

    def test_secrets_are_properly_masked_in_string_representation(self) -> None:
        """Test that sensitive fields are properly masked in string representation."""
        env_vars = {
            "HULEEDU_DB_PASSWORD": "super_secret_db_password_åäö",
            "HULEEDU_INTERNAL_API_KEY": "secret_api_key_ÅÄÖ",
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "test_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            settings_str = str(settings)

            # Secrets should be properly masked
            assert "super_secret_db_password_åäö" not in settings_str
            assert "secret_api_key_ÅÄÖ" not in settings_str
            assert "***MASKED***" in settings_str

            # Non-sensitive values should be present
            assert "entitlements_service" in settings_str
            assert "development" in settings_str

    def test_repr_properly_masks_secrets(self) -> None:
        """Test that repr() properly masks sensitive information."""
        env_vars = {
            "HULEEDU_DB_PASSWORD": "secret_in_repr_åäö",
            "HULEEDU_INTERNAL_API_KEY": "api_key_in_repr_ÅÄÖ",
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "test_user",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            settings_repr = repr(settings)

            # Secrets should be properly masked in repr
            assert "secret_in_repr_åäö" not in settings_repr
            assert "api_key_in_repr_ÅÄÖ" not in settings_repr
            assert "***MASKED***" in settings_repr

            # Verify repr and str provide the same secure representation
            assert repr(settings) == str(settings)

    def test_environment_variable_prefix_isolation(self) -> None:
        """Test that only ENTITLEMENTS_ prefixed environment variables are used."""
        env_vars = {
            "ENTITLEMENTS_SERVICE_NAME": "correct_entitlements_service",
            "SERVICE_NAME": "wrong_service_name",  # Should be ignored
            "ENTITLEMENTS_LOG_LEVEL": "DEBUG",
            "LOG_LEVEL": "ERROR",  # Should be ignored
            "ENTITLEMENTS_DEFAULT_USER_CREDITS": "100",
            "DEFAULT_USER_CREDITS": "999",  # Should be ignored
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            # Should use the ENTITLEMENTS_ prefixed versions
            assert settings.SERVICE_NAME == "correct_entitlements_service"
            assert settings.LOG_LEVEL == "DEBUG"
            assert settings.DEFAULT_USER_CREDITS == 100

    def test_settings_extra_ignore_behavior(self) -> None:
        """Test that extra environment variables are ignored due to model_config extra='ignore'."""
        env_vars = {
            "ENTITLEMENTS_UNKNOWN_FIELD": "should_be_ignored",
            "ENTITLEMENTS_ANOTHER_FIELD": "also_ignored",
            "ENTITLEMENTS_SERVICE_NAME": "valid_service_name",
            "ENTITLEMENTS_FAKE_CREDIT_SETTING": "ignored_credit_value",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise an error due to extra='ignore'
            settings = Settings()
            assert settings.SERVICE_NAME == "valid_service_name"

            # Unknown fields should not be accessible
            assert not hasattr(settings, "UNKNOWN_FIELD")
            assert not hasattr(settings, "ANOTHER_FIELD")
            assert not hasattr(settings, "FAKE_CREDIT_SETTING")

    def test_zero_value_integer_environment_variables(self) -> None:
        """Test handling of zero values for integer environment variables."""
        with patch.dict(
            os.environ, {"ENTITLEMENTS_POLICY_CACHE_TTL": "0", "ENTITLEMENTS_METRICS_PORT": "0"}
        ):
            settings = Settings()
            assert settings.POLICY_CACHE_TTL == 0
            assert settings.METRICS_PORT == 0
            assert isinstance(settings.POLICY_CACHE_TTL, int)
            assert isinstance(settings.METRICS_PORT, int)

    @pytest.mark.parametrize(
        "field_name, large_value",
        [
            ("POLICY_CACHE_TTL", 2147483647),
            ("DEFAULT_USER_CREDITS", 2147483647),
            ("METRICS_PORT", 65535),  # Max port number
        ],
    )
    def test_very_large_integer_environment_variables(
        self, field_name: str, large_value: int
    ) -> None:
        """Test handling of very large integer values."""
        env_var = f"ENTITLEMENTS_{field_name}"

        with patch.dict(os.environ, {env_var: str(large_value)}):
            settings = Settings()
            actual_value = getattr(settings, field_name)
            assert actual_value == large_value

    @pytest.mark.parametrize(
        "field_name, boolean_string_value",
        [
            ("SERVICE_NAME", "true"),
            ("POLICY_FILE", "True"),
            ("LOG_LEVEL", "yes"),
        ],
    )
    def test_boolean_like_string_values_for_non_boolean_fields(
        self, field_name: str, boolean_string_value: str
    ) -> None:
        """Test that boolean-like strings are handled correctly for non-boolean fields."""
        env_var = f"ENTITLEMENTS_{field_name}"

        with patch.dict(os.environ, {env_var: boolean_string_value}):
            settings = Settings()
            actual_value = getattr(settings, field_name)
            # Should be treated as literal strings, not booleans
            assert actual_value == boolean_string_value
            assert isinstance(actual_value, str)

    def test_edge_case_empty_string_environment_variables(self) -> None:
        """Test handling of empty string environment variables."""
        env_vars = {
            "ENTITLEMENTS_SERVICE_NAME": "",
            "ENTITLEMENTS_POLICY_FILE": "",
            "ENTITLEMENTS_LOG_LEVEL": "",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            # Empty strings should be treated as valid values
            assert settings.SERVICE_NAME == ""
            assert settings.POLICY_FILE == ""
            assert settings.LOG_LEVEL == ""

    @pytest.mark.parametrize(
        "boolean_field, env_var, truthy_value, falsy_value",
        [
            ("USE_MOCK_REPOSITORY", "ENTITLEMENTS_USE_MOCK_REPOSITORY", "true", "false"),
            ("RATE_LIMIT_ENABLED", "ENTITLEMENTS_RATE_LIMIT_ENABLED", "TRUE", "FALSE"),
            ("CIRCUIT_BREAKER_ENABLED", "ENTITLEMENTS_CIRCUIT_BREAKER_ENABLED", "1", "0"),
        ],
    )
    def test_boolean_field_string_conversion(
        self, boolean_field: str, env_var: str, truthy_value: str, falsy_value: str
    ) -> None:
        """Test boolean fields properly convert string environment variables."""
        with patch.dict(os.environ, {env_var: truthy_value}):
            settings = Settings()
            assert getattr(settings, boolean_field) is True

        with patch.dict(os.environ, {env_var: falsy_value}):
            settings = Settings()
            assert getattr(settings, boolean_field) is False

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
    ) -> None:
        """Test that environment detection methods work correctly."""
        with patch.dict(os.environ, {"ENVIRONMENT": env_value}):
            settings = Settings()
            assert settings.is_development() == is_dev
            assert settings.is_staging() == is_staging
            assert settings.is_production() == is_prod
            assert settings.is_testing() == is_testing
            assert settings.requires_security() == requires_security
