"""
Unit tests for identity service configuration validation.

Tests the Settings class for environment variable handling, database URL generation,
default values, secret masking, and validation errors following Rule 075 methodology.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from common_core.config_enums import Environment
from pydantic import SecretStr, ValidationError

from services.identity_service.config import Settings


class TestIdentityServiceSettings:
    """Tests for identity service configuration validation."""

    def test_settings_loads_default_values(self) -> None:
        """Test that Settings loads correct default values when no environment variables are set."""
        # Clear any existing environment variables that might interfere
        env_vars_to_clear = [
            "IDENTITY_SERVICE_NAME",
            "IDENTITY_SERVICE_VERSION", 
            "IDENTITY_LOG_LEVEL",
            "IDENTITY_REDIS_URL",
            "IDENTITY_KAFKA_BOOTSTRAP_SERVERS",
            "IDENTITY_JWT_DEV_SECRET",
            "IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS",
            "ENVIRONMENT",
        ]
        
        with patch.dict(os.environ, {}, clear=False):
            # Remove specific environment variables
            for var in env_vars_to_clear:
                os.environ.pop(var, None)
            
            settings = Settings()
            
            # Test service identity defaults
            assert settings.SERVICE_NAME == "identity_service"
            assert settings.SERVICE_VERSION == "0.1.0"
            
            # Test logging and environment defaults
            assert settings.LOG_LEVEL == "INFO"
            assert settings.ENVIRONMENT == Environment.DEVELOPMENT
            
            # Test Redis and Kafka defaults
            assert settings.REDIS_URL == "redis://localhost:6379/0"
            assert settings.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"
            
            # Test JWT configuration defaults
            assert settings.JWT_DEV_SECRET.get_secret_value() == "dev-secret-change-me"
            assert settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS == 3600
            
            # Test optional RS256 fields default to None
            assert settings.JWT_RS256_PRIVATE_KEY_PATH is None
            assert settings.JWT_RS256_PUBLIC_JWKS_KID is None

    @pytest.mark.parametrize(
        "env_var, value, field_name, expected",
        [
            ("IDENTITY_SERVICE_NAME", "custom_identity", "SERVICE_NAME", "custom_identity"),
            ("IDENTITY_SERVICE_VERSION", "1.0.0", "SERVICE_VERSION", "1.0.0"),
            ("IDENTITY_LOG_LEVEL", "DEBUG", "LOG_LEVEL", "DEBUG"),
            ("IDENTITY_REDIS_URL", "redis://prod:6379/1", "REDIS_URL", "redis://prod:6379/1"),
            ("IDENTITY_KAFKA_BOOTSTRAP_SERVERS", "broker1:9092,broker2:9092", "KAFKA_BOOTSTRAP_SERVERS", "broker1:9092,broker2:9092"),
            ("IDENTITY_JWT_DEV_SECRET", "custom-dev-secret", "JWT_DEV_SECRET", "custom-dev-secret"),
            ("IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "7200", "JWT_ACCESS_TOKEN_EXPIRES_SECONDS", 7200),
            ("IDENTITY_JWT_RS256_PRIVATE_KEY_PATH", "/path/to/key.pem", "JWT_RS256_PRIVATE_KEY_PATH", "/path/to/key.pem"),
            ("IDENTITY_JWT_RS256_PUBLIC_JWKS_KID", "key-id-123", "JWT_RS256_PUBLIC_JWKS_KID", "key-id-123"),
        ],
    )
    def test_environment_variable_loading_with_prefix(
        self, env_var: str, value: str, field_name: str, expected: str | int
    ) -> None:
        """Test that environment variables are loaded correctly with IDENTITY_ prefix."""
        with patch.dict(os.environ, {env_var: value}):
            settings = Settings()
            actual_value = getattr(settings, field_name)
            
            # Handle SecretStr fields by comparing secret values
            if hasattr(actual_value, 'get_secret_value'):
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

    def test_integer_type_coercion_from_environment(self) -> None:
        """Test that string environment variables are correctly coerced to integers."""
        with patch.dict(os.environ, {"IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS": "1800"}):
            settings = Settings()
            assert settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS == 1800
            assert isinstance(settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS, int)

    def test_invalid_integer_environment_variable_raises_validation_error(self) -> None:
        """Test that invalid integer values in environment variables raise ValidationError."""
        with patch.dict(os.environ, {"IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS": "not_a_number"}):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            
            # Verify the error is about type validation
            assert "JWT_ACCESS_TOKEN_EXPIRES_SECONDS" in str(exc_info.value)

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
            database_url = settings.database_url
            
            expected_url = "postgresql+asyncpg://test_user:test_password@localhost:5442/huleedu_identity"
            assert database_url == expected_url

    def test_database_url_production_environment_correctly_detected(self) -> None:
        """Test database URL generation for production environment with correct implementation.
        
        The production environment is now correctly detected using is_production() method,
        which properly compares enum values and uses production database configuration.
        """
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "prod.db.example.com",
            "HULEEDU_PROD_DB_PORT": "5433", 
            "HULEEDU_PROD_DB_PASSWORD": "secure_prod_password",
            "HULEEDU_DB_USER": "test_user",
            "HULEEDU_DB_PASSWORD": "test_password",
        }
        
        # Clear the .env loaded variables to avoid interference
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            database_url = settings.database_url
            
            # Now correctly uses production database configuration
            expected_url = "postgresql+asyncpg://test_user:secure_prod_password@prod.db.example.com:5433/huleedu_identity"
            assert database_url == expected_url

    def test_database_url_production_environment_with_default_port(self) -> None:
        """Test production environment detection with default port configuration.
        
        Verifies that production environment correctly uses default port 5432 when
        HULEEDU_PROD_DB_PORT is not specified.
        """
        env_vars = {
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "prod.db.example.com",
            "HULEEDU_PROD_DB_PASSWORD": "secure_prod_password",
            "HULEEDU_DB_USER": "test_user",
            "HULEEDU_DB_PASSWORD": "test_password",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            # The enum is correctly set to PRODUCTION
            assert settings.ENVIRONMENT == Environment.PRODUCTION
            
            # Production URL uses the correct production configuration with default port
            database_url = settings.database_url
            
            expected_production_url = "postgresql+asyncpg://test_user:secure_prod_password@prod.db.example.com:5432/huleedu_identity"
            assert database_url == expected_production_url

    def test_database_url_service_override(self) -> None:
        """Test that SERVICE_DATABASE_URL environment variable overrides database URL generation."""
        override_url = "postgresql+asyncpg://override_user:override_pass@override.host:5555/override_db"
        env_vars = {
            "IDENTITY_SERVICE_DATABASE_URL": override_url,
            "ENVIRONMENT": "production",
            "HULEEDU_PROD_DB_HOST": "should_be_ignored.com",
            "HULEEDU_PROD_DB_PASSWORD": "should_be_ignored",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.database_url == override_url

    def test_database_url_generic_service_override(self) -> None:
        """Test that generic SERVICE_DATABASE_URL environment variable overrides database URL generation."""
        override_url = "postgresql+asyncpg://generic_user:generic_pass@generic.host:5555/generic_db"
        env_vars = {
            "SERVICE_DATABASE_URL": override_url,
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "should_be_ignored",
            "HULEEDU_DB_PASSWORD": "should_be_ignored",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.database_url == override_url

    def test_database_url_production_validation_enforced(self) -> None:
        """Test that production validation is properly enforced with correct environment detection.
        
        Production environment now correctly validates required environment variables
        and raises appropriate errors when they are missing.
        """
        env_vars = {
            "ENVIRONMENT": "production",
            # Intentionally missing HULEEDU_PROD_DB_HOST and HULEEDU_PROD_DB_PASSWORD
            "HULEEDU_DB_USER": "test_user",
            "HULEEDU_DB_PASSWORD": "test_password",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            # Production validation should now be triggered and raise ValueError
            with pytest.raises(ValueError) as exc_info:
                _ = settings.database_url
            
            # Verify the error mentions the missing production variables
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
                _ = settings.database_url
            
            assert "HULEEDU_DB_USER" in str(exc_info.value)

    def test_database_url_development_missing_password_raises_error(self) -> None:
        """Test that missing development database password raises ValueError."""
        env_vars = {
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "dev_user",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            with pytest.raises(ValueError) as exc_info:
                _ = settings.database_url
            
            assert "HULEEDU_DB_PASSWORD" in str(exc_info.value)

    def test_swedish_characters_in_configuration_values(self) -> None:
        """Test that Swedish characters are properly handled in configuration values."""
        swedish_service_name = "identitet_tjänst_åäö"
        swedish_secret = "hemlig_nyckel_ÅÄÖ"
        
        env_vars = {
            "IDENTITY_SERVICE_NAME": swedish_service_name,
            "IDENTITY_JWT_DEV_SECRET": swedish_secret,
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.SERVICE_NAME == swedish_service_name
            assert settings.JWT_DEV_SECRET.get_secret_value() == swedish_secret

    def test_secrets_are_properly_masked_in_string_representation(self) -> None:
        """Test that sensitive fields are properly masked in string representation.
        
        The Settings class now implements proper secret masking to prevent
        accidental exposure of sensitive data in logs and debug output.
        """
        env_vars = {
            "IDENTITY_JWT_DEV_SECRET": "super_secret_jwt_key",
            "HULEEDU_DB_PASSWORD": "super_secret_db_password",
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "test_user",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            settings_str = str(settings)
            
            # SECURITY FIX: Secrets are now properly masked
            assert "super_secret_jwt_key" not in settings_str
            assert "***MASKED***" in settings_str
            
            # Check that non-sensitive values are still present
            assert "identity_service" in settings_str
            assert "development" in settings_str
            
            # Database URL masking can be tested separately with database_url_masked property
            masked_url = settings.database_url_masked
            assert "super_secret_db_password" not in masked_url
            assert "***" in masked_url

    def test_repr_properly_masks_secrets(self) -> None:
        """Test that repr() properly masks sensitive information.
        
        The repr() method now uses the same secure string representation
        as __str__() to prevent accidental exposure of secrets.
        """
        env_vars = {
            "IDENTITY_JWT_DEV_SECRET": "secret_in_repr",
            "HULEEDU_DB_PASSWORD": "db_password_in_repr",
            "ENVIRONMENT": "development",
            "HULEEDU_DB_USER": "test_user",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            settings_repr = repr(settings)
            
            # SECURITY FIX: Secrets are now properly masked in repr
            assert "secret_in_repr" not in settings_repr
            assert "***MASKED***" in settings_repr
            
            # Verify repr and str provide the same secure representation
            assert repr(settings) == str(settings)

    def test_environment_variable_prefix_isolation(self) -> None:
        """Test that only IDENTITY_ prefixed environment variables are used."""
        env_vars = {
            "IDENTITY_SERVICE_NAME": "correct_identity_service",
            "SERVICE_NAME": "wrong_service_name",  # Should be ignored
            "IDENTITY_LOG_LEVEL": "DEBUG",
            "LOG_LEVEL": "ERROR",  # Should be ignored
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            # Should use the IDENTITY_ prefixed versions
            assert settings.SERVICE_NAME == "correct_identity_service"
            assert settings.LOG_LEVEL == "DEBUG"

    def test_settings_extra_ignore_behavior(self) -> None:
        """Test that extra environment variables are ignored due to model_config extra='ignore'."""
        env_vars = {
            "IDENTITY_UNKNOWN_FIELD": "should_be_ignored",
            "IDENTITY_ANOTHER_FIELD": "also_ignored",
            "IDENTITY_SERVICE_NAME": "valid_service_name",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise an error due to extra='ignore'
            settings = Settings()
            assert settings.SERVICE_NAME == "valid_service_name"
            
            # Unknown fields should not be accessible
            assert not hasattr(settings, "UNKNOWN_FIELD")
            assert not hasattr(settings, "ANOTHER_FIELD")

    def test_edge_case_empty_string_environment_variables(self) -> None:
        """Test handling of empty string environment variables."""
        env_vars = {
            "IDENTITY_SERVICE_NAME": "",
            "IDENTITY_JWT_DEV_SECRET": "",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            # Empty strings should be treated as valid values
            assert settings.SERVICE_NAME == ""
            assert settings.JWT_DEV_SECRET.get_secret_value() == ""

    def test_zero_value_integer_environment_variables(self) -> None:
        """Test handling of zero values for integer environment variables."""
        with patch.dict(os.environ, {"IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS": "0"}, clear=True):
            settings = Settings()
            assert settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS == 0
            assert isinstance(settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS, int)

    def test_very_large_integer_environment_variables(self) -> None:
        """Test handling of very large integer values."""
        large_value = "2147483647"  # Max 32-bit signed integer
        with patch.dict(os.environ, {"IDENTITY_JWT_ACCESS_TOKEN_EXPIRES_SECONDS": large_value}, clear=True):
            settings = Settings()
            assert settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS == 2147483647

    def test_boolean_like_string_values_for_non_boolean_fields(self) -> None:
        """Test that boolean-like strings are handled correctly for non-boolean fields."""
        env_vars = {
            "IDENTITY_SERVICE_NAME": "true",
            "IDENTITY_SERVICE_VERSION": "false",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            # Should be treated as literal strings, not booleans
            assert settings.SERVICE_NAME == "true"
            assert settings.SERVICE_VERSION == "false"