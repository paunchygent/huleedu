"""
Security test suite to validate secret masking across all services.

This test suite ensures that:
1. All service configurations properly mask secrets in string representations
2. Environment detection helpers work correctly
3. SecretStr fields are properly configured
4. No secrets are exposed in logs or error messages
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from huleedu_service_libs.config import SecureServiceSettings

# Import all service configs to test them
from services.api_gateway_service.config import Settings as APIGatewaySettings
from services.batch_conductor_service.config import Settings as BatchConductorSettings
from services.batch_orchestrator_service.config import Settings as BatchOrchestratorSettings
from services.cj_assessment_service.config import Settings as CJAssessmentSettings
from services.class_management_service.config import Settings as ClassManagementSettings
from services.content_service.config import Settings as ContentSettings
from services.essay_lifecycle_service.config import Settings as EssayLifecycleSettings
from services.file_service.config import Settings as FileSettings
from services.identity_service.config import Settings as IdentitySettings
from services.llm_provider_service.config import Settings as LLMProviderSettings
from services.nlp_service.config import Settings as NLPSettings
from services.result_aggregator_service.config import Settings as ResultAggregatorSettings
from services.spellchecker_service.config import Settings as SpellcheckerSettings
from services.websocket_service.config import Settings as WebSocketSettings


# All service configurations to test
ALL_SERVICE_CONFIGS = [
    ("api_gateway_service", APIGatewaySettings),
    ("batch_conductor_service", BatchConductorSettings),
    ("batch_orchestrator_service", BatchOrchestratorSettings),
    ("cj_assessment_service", CJAssessmentSettings),
    ("class_management_service", ClassManagementSettings),
    ("content_service", ContentSettings),
    ("essay_lifecycle_service", EssayLifecycleSettings),
    ("file_service", FileSettings),
    ("identity_service", IdentitySettings),
    ("llm_provider_service", LLMProviderSettings),
    ("nlp_service", NLPSettings),
    ("result_aggregator_service", ResultAggregatorSettings),
    ("spellchecker_service", SpellcheckerSettings),
    ("websocket_service", WebSocketSettings),
]


class TestSecretMasking:
    """Test suite for secret masking across all services."""

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_service_inherits_from_secure_base(self, service_name: str, settings_class):
        """Test that all services inherit from SecureServiceSettings."""
        settings = settings_class()
        assert isinstance(settings, SecureServiceSettings), (
            f"{service_name} does not inherit from SecureServiceSettings"
        )

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_string_representation_masks_secrets(self, service_name: str, settings_class):
        """Test that __str__ method masks all secrets."""
        settings = settings_class()
        str_repr = str(settings)

        # Should contain masked secrets indicator
        assert "***MASKED***" in str_repr, (
            f"{service_name} string representation does not mask secrets"
        )

        # Should contain service name and environment
        assert service_name.replace("_", "-") in str_repr or settings.SERVICE_NAME in str_repr
        assert settings.ENVIRONMENT.value in str_repr

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_repr_method_masks_secrets(self, service_name: str, settings_class):
        """Test that __repr__ method also masks secrets."""
        settings = settings_class()
        repr_str = repr(settings)

        # Should contain masked secrets indicator
        assert "***MASKED***" in repr_str, f"{service_name} repr does not mask secrets"

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_environment_detection_helpers(self, service_name: str, settings_class):
        """Test that environment detection helper methods work correctly."""
        settings = settings_class()

        # Should have all helper methods
        assert hasattr(settings, "is_production"), f"{service_name} missing is_production() method"
        assert hasattr(settings, "is_development"), (
            f"{service_name} missing is_development() method"
        )
        assert hasattr(settings, "is_staging"), f"{service_name} missing is_staging() method"
        assert hasattr(settings, "is_testing"), f"{service_name} missing is_testing() method"
        assert hasattr(settings, "requires_security"), (
            f"{service_name} missing requires_security() method"
        )

        # Should return booleans
        assert isinstance(settings.is_production(), bool)
        assert isinstance(settings.is_development(), bool)
        assert isinstance(settings.is_staging(), bool)
        assert isinstance(settings.is_testing(), bool)
        assert isinstance(settings.requires_security(), bool)

    def test_llm_provider_service_api_keys_are_secret_str(self):
        """Test that LLM Provider Service API keys are SecretStr."""
        settings = LLMProviderSettings()

        # Check all API keys are SecretStr
        assert isinstance(settings.OPENAI_API_KEY, SecretStr), "OPENAI_API_KEY is not SecretStr"
        assert isinstance(settings.ANTHROPIC_API_KEY, SecretStr), (
            "ANTHROPIC_API_KEY is not SecretStr"
        )
        assert isinstance(settings.GOOGLE_API_KEY, SecretStr), "GOOGLE_API_KEY is not SecretStr"
        assert isinstance(settings.OPENROUTER_API_KEY, SecretStr), (
            "OPENROUTER_API_KEY is not SecretStr"
        )
        # ADMIN_API_KEY is optional, only check if not None
        if settings.ADMIN_API_KEY is not None:
            assert isinstance(settings.ADMIN_API_KEY, SecretStr), (
                "ADMIN_API_KEY is not SecretStr when present"
            )

    def test_api_gateway_jwt_secret_is_secret_str(self):
        """Test that API Gateway JWT secret is SecretStr."""
        settings = APIGatewaySettings()
        assert isinstance(settings.JWT_SECRET_KEY, SecretStr), "JWT_SECRET_KEY is not SecretStr"

    def test_websocket_service_jwt_secret_is_secret_str(self):
        """Test that WebSocket Service JWT secret is SecretStr."""
        settings = WebSocketSettings()
        assert isinstance(settings.JWT_SECRET_KEY, SecretStr), "JWT_SECRET_KEY is not SecretStr"

    def test_identity_service_jwt_secret_is_secret_str(self):
        """Test that Identity Service JWT secret is SecretStr."""
        settings = IdentitySettings()
        assert isinstance(settings.JWT_DEV_SECRET, SecretStr), "JWT_DEV_SECRET is not SecretStr"

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_shared_secrets_inherited_from_base(self, service_name: str, settings_class):
        """Test that shared secrets are properly inherited from SecureServiceSettings."""
        settings = settings_class()

        # Should have shared secrets from base class
        assert hasattr(settings, "DB_PASSWORD"), f"{service_name} missing DB_PASSWORD"
        assert hasattr(settings, "INTERNAL_API_KEY"), f"{service_name} missing INTERNAL_API_KEY"

        # Should be SecretStr
        assert isinstance(settings.DB_PASSWORD, SecretStr), (
            f"{service_name} DB_PASSWORD is not SecretStr"
        )
        assert isinstance(settings.INTERNAL_API_KEY, SecretStr), (
            f"{service_name} INTERNAL_API_KEY is not SecretStr"
        )

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_secret_helper_methods(self, service_name: str, settings_class):
        """Test that secret helper methods are available."""
        settings = settings_class()

        # Should have helper methods
        assert hasattr(settings, "get_db_password"), (
            f"{service_name} missing get_db_password() method"
        )
        assert hasattr(settings, "get_internal_api_key"), (
            f"{service_name} missing get_internal_api_key() method"
        )

        # Should return strings
        assert isinstance(settings.get_db_password(), str)
        assert isinstance(settings.get_internal_api_key(), str)

    def test_database_url_masking(self):
        """Test database URL masking functionality."""
        settings = SecureServiceSettings()

        # Test database URL masking
        test_url = "postgresql+asyncpg://user:secret_password@localhost:5432/db"
        masked_url = settings.database_url_masked(test_url)

        assert "secret_password" not in masked_url, "Database URL still contains password"
        assert "***" in masked_url, "Database URL does not contain masking"
        # The regex replaces with \\1 which is the backreference, check for username differently
        assert "user" in masked_url, "Database URL missing username reference"
        assert "@localhost:5432/db" in masked_url, "Database URL missing connection details"

    def test_no_secrets_in_log_representation(self):
        """Test that secrets don't appear in any string representation."""
        # Test with settings that have known secrets
        settings = LLMProviderSettings()

        # Get secret values for comparison (skip if empty)
        openai_key = settings.OPENAI_API_KEY.get_secret_value()
        anthropic_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        
        # Skip test if secrets are empty (default values)
        if not openai_key or not anthropic_key:
            pytest.skip("API keys are empty, skipping secret leak test")

        # Test string representation
        str_repr = str(settings)
        assert openai_key not in str_repr, "OpenAI API key found in string representation"
        assert anthropic_key not in str_repr, "Anthropic API key found in string representation"

        # Test repr
        repr_str = repr(settings)
        assert openai_key not in repr_str, "OpenAI API key found in repr"
        assert anthropic_key not in repr_str, "Anthropic API key found in repr"


class TestEnvironmentDetection:
    """Test environment detection standardization."""

    @pytest.mark.parametrize("service_name,settings_class", ALL_SERVICE_CONFIGS)
    def test_environment_enum_usage(self, service_name: str, settings_class):
        """Test that services use Environment enum instead of strings."""
        settings = settings_class()

        from common_core.config_enums import Environment

        # ENVIRONMENT field should be Environment enum type
        assert isinstance(settings.ENVIRONMENT, Environment), (
            f"{service_name} ENVIRONMENT is not Environment enum"
        )

    def test_production_environment_detection(self):
        """Test production environment detection works correctly."""
        from common_core.config_enums import Environment

        # Create settings with production environment
        settings = SecureServiceSettings(ENVIRONMENT=Environment.PRODUCTION)

        assert settings.is_production() is True
        assert settings.is_development() is False
        assert settings.requires_security() is True

    def test_development_environment_detection(self):
        """Test development environment detection works correctly."""
        from common_core.config_enums import Environment

        # Create settings with development environment
        settings = SecureServiceSettings(ENVIRONMENT=Environment.DEVELOPMENT)

        assert settings.is_production() is False
        assert settings.is_development() is True
        assert settings.requires_security() is False


class TestSecretAccess:
    """Test proper secret access patterns."""

    def test_secret_str_get_secret_value(self):
        """Test that SecretStr values can be extracted properly."""
        settings = APIGatewaySettings()

        # Should be able to get secret value
        jwt_secret = settings.JWT_SECRET_KEY.get_secret_value()
        assert isinstance(jwt_secret, str)
        assert len(jwt_secret) > 0

    def test_helper_methods_return_plain_strings(self):
        """Test that helper methods return plain string values."""
        settings = SecureServiceSettings()

        db_password = settings.get_db_password()
        internal_api_key = settings.get_internal_api_key()

        assert isinstance(db_password, str)
        assert isinstance(internal_api_key, str)
