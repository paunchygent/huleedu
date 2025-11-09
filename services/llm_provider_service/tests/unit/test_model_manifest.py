"""Unit tests for LLM Provider Service model manifest.

Tests cover:
- Registry validation (Pydantic schema enforcement)
- Model lookup by provider and ID
- Default model resolution
- Error handling for unknown models/providers
- Capability validation
- Model config immutability (frozen)
"""

from datetime import date

import pytest
from pydantic import ValidationError

from services.llm_provider_service.model_manifest import (
    SUPPORTED_MODELS,
    ModelConfig,
    ModelRegistry,
    ProviderName,
    StructuredOutputMethod,
    get_default_model_id,
    get_model_config,
    list_models,
    validate_model_capability,
)


class TestModelConfigSchema:
    """Test ModelConfig Pydantic validation."""

    def test_valid_model_config_creation(self) -> None:
        """Valid ModelConfig should be created successfully."""
        config = ModelConfig(
            model_id="test-model-123",
            provider=ProviderName.ANTHROPIC,
            display_name="Test Model",
            api_version="2023-06-01",
            structured_output_method=StructuredOutputMethod.TOOL_USE,
            capabilities={"tool_use": True, "vision": False},
            max_tokens=4096,
            context_window=200_000,
            supports_streaming=True,
            release_date=date(2024, 1, 1),
            is_deprecated=False,
            cost_per_1k_input_tokens=0.001,
            cost_per_1k_output_tokens=0.002,
            recommended_for=["testing", "validation"],
            notes="Test model for unit tests",
        )

        assert config.model_id == "test-model-123"
        assert config.provider == ProviderName.ANTHROPIC
        assert config.display_name == "Test Model"
        assert config.api_version == "2023-06-01"
        assert config.structured_output_method == StructuredOutputMethod.TOOL_USE
        assert config.capabilities["tool_use"] is True
        assert config.max_tokens == 4096

    def test_model_config_with_minimal_fields(self) -> None:
        """ModelConfig should work with only required fields."""
        config = ModelConfig(
            model_id="minimal-model",
            provider=ProviderName.OPENAI,
            display_name="Minimal Model",
            api_version="v1",
            structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        )

        # Check defaults are applied
        assert config.capabilities == {}
        assert config.max_tokens == 4096
        assert config.context_window == 200_000
        assert config.supports_streaming is True
        assert config.release_date is None
        assert config.is_deprecated is False
        assert config.cost_per_1k_input_tokens is None
        assert config.recommended_for == []
        assert config.notes == ""

    def test_model_config_is_frozen(self) -> None:
        """ModelConfig should be immutable (frozen)."""
        config = ModelConfig(
            model_id="frozen-test",
            provider=ProviderName.ANTHROPIC,
            display_name="Frozen Test",
            api_version="2023-06-01",
            structured_output_method=StructuredOutputMethod.TOOL_USE,
        )

        with pytest.raises(ValidationError, match="frozen"):
            config.model_id = "modified"  # type: ignore

    def test_invalid_provider_name_rejected(self) -> None:
        """Invalid provider names should be rejected."""
        with pytest.raises(ValidationError):
            ModelConfig(
                model_id="test",
                provider="invalid_provider",  # type: ignore
                display_name="Test",
                api_version="v1",
                structured_output_method=StructuredOutputMethod.TOOL_USE,
            )

    def test_invalid_structured_output_method_rejected(self) -> None:
        """Invalid structured output methods should be rejected."""
        with pytest.raises(ValidationError):
            ModelConfig(
                model_id="test",
                provider=ProviderName.ANTHROPIC,
                display_name="Test",
                api_version="v1",
                structured_output_method="invalid_method",  # type: ignore
            )


class TestModelRegistry:
    """Test ModelRegistry structure and validation."""

    def test_supported_models_registry_structure(self) -> None:
        """SUPPORTED_MODELS should have correct structure."""
        assert isinstance(SUPPORTED_MODELS, ModelRegistry)
        assert isinstance(SUPPORTED_MODELS.models, dict)
        assert isinstance(SUPPORTED_MODELS.default_models, dict)

        # All providers should be present
        assert ProviderName.ANTHROPIC in SUPPORTED_MODELS.models
        assert ProviderName.OPENAI in SUPPORTED_MODELS.models
        assert ProviderName.GOOGLE in SUPPORTED_MODELS.models
        assert ProviderName.OPENROUTER in SUPPORTED_MODELS.models
        assert ProviderName.MOCK in SUPPORTED_MODELS.models

    def test_anthropic_models_populated(self) -> None:
        """Anthropic should have at least one model."""
        anthropic_models = SUPPORTED_MODELS.models[ProviderName.ANTHROPIC]
        assert len(anthropic_models) >= 1

        # Check primary model exists
        haiku_exists = any(m.model_id == "claude-haiku-4-5-20251001" for m in anthropic_models)
        assert haiku_exists, "Primary Anthropic model (Haiku) should be in manifest"

    def test_all_providers_have_defaults(self) -> None:
        """All non-mock providers should have default models."""
        for provider in [
            ProviderName.ANTHROPIC,
            ProviderName.OPENAI,
            ProviderName.GOOGLE,
            ProviderName.OPENROUTER,
        ]:
            default_id = SUPPORTED_MODELS.default_models.get(provider)
            assert default_id is not None, f"{provider} should have a default model"
            assert isinstance(default_id, str)
            assert len(default_id) > 0

    def test_default_models_exist_in_registry(self) -> None:
        """Default models should actually exist in the models list."""
        for provider, default_id in SUPPORTED_MODELS.default_models.items():
            if provider == ProviderName.MOCK:
                continue  # Mock has no models

            provider_models = SUPPORTED_MODELS.models[provider]
            model_ids = [m.model_id for m in provider_models]

            assert default_id in model_ids, (
                f"Default model '{default_id}' not found in {provider} models: {model_ids}"
            )


class TestGetModelConfig:
    """Test get_model_config() function."""

    def test_get_default_anthropic_model(self) -> None:
        """Should return default Anthropic model when no ID specified."""
        config = get_model_config(ProviderName.ANTHROPIC)

        assert config.provider == ProviderName.ANTHROPIC
        assert config.model_id == "claude-haiku-4-5-20251001"
        assert config.display_name == "Claude Haiku 4.5"
        assert config.api_version == "2023-06-01"
        assert config.structured_output_method == StructuredOutputMethod.TOOL_USE

    def test_get_specific_anthropic_model(self) -> None:
        """Should return specific model when ID provided."""
        config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")

        assert config.model_id == "claude-haiku-4-5-20251001"
        assert config.provider == ProviderName.ANTHROPIC

    def test_get_default_openai_model(self) -> None:
        """Should return default OpenAI model."""
        config = get_model_config(ProviderName.OPENAI)

        assert config.provider == ProviderName.OPENAI
        assert config.model_id == "gpt-5-mini-2025-08-07"

    def test_get_default_google_model(self) -> None:
        """Should return default Google model."""
        config = get_model_config(ProviderName.GOOGLE)

        assert config.provider == ProviderName.GOOGLE
        assert config.model_id == "gemini-2.5-flash-preview-05-20"

    def test_get_default_openrouter_model(self) -> None:
        """Should return default OpenRouter model."""
        config = get_model_config(ProviderName.OPENROUTER)

        assert config.provider == ProviderName.OPENROUTER
        assert config.model_id == "anthropic/claude-haiku-4-5-20251001"

    def test_unknown_provider_raises_error(self) -> None:
        """Should raise ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            # Invalid provider not in enum
            get_model_config("invalid_provider")  # type: ignore

    def test_unknown_model_id_raises_error(self) -> None:
        """Should raise ValueError for unknown model ID."""
        with pytest.raises(ValueError, match="not found"):
            get_model_config(ProviderName.ANTHROPIC, "nonexistent-model-123")

    def test_error_message_lists_available_models(self) -> None:
        """Error for unknown model should list available models."""
        with pytest.raises(ValueError) as exc_info:
            get_model_config(ProviderName.ANTHROPIC, "invalid-model")

        error_msg = str(exc_info.value)
        assert "Available models:" in error_msg
        assert "claude-haiku-4-5-20251001" in error_msg


class TestGetDefaultModelId:
    """Test get_default_model_id() function."""

    def test_get_anthropic_default_id(self) -> None:
        """Should return correct default ID for Anthropic."""
        model_id = get_default_model_id(ProviderName.ANTHROPIC)
        assert model_id == "claude-haiku-4-5-20251001"

    def test_get_openai_default_id(self) -> None:
        """Should return correct default ID for OpenAI."""
        model_id = get_default_model_id(ProviderName.OPENAI)
        assert model_id == "gpt-5-mini-2025-08-07"

    def test_get_google_default_id(self) -> None:
        """Should return correct default ID for Google."""
        model_id = get_default_model_id(ProviderName.GOOGLE)
        assert model_id == "gemini-2.5-flash-preview-05-20"

    def test_get_openrouter_default_id(self) -> None:
        """Should return correct default ID for OpenRouter."""
        model_id = get_default_model_id(ProviderName.OPENROUTER)
        assert model_id == "anthropic/claude-haiku-4-5-20251001"

    def test_unknown_provider_raises_error(self) -> None:
        """Should raise ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_default_model_id("invalid")  # type: ignore


class TestListModels:
    """Test list_models() function."""

    def test_list_all_models(self) -> None:
        """Should return all models when no provider specified."""
        all_models = list_models()

        assert isinstance(all_models, list)
        assert len(all_models) >= 4  # At least one per non-mock provider

        # Check models from different providers are included
        providers_found = {m.provider for m in all_models}
        assert ProviderName.ANTHROPIC in providers_found
        assert ProviderName.OPENAI in providers_found
        assert ProviderName.GOOGLE in providers_found
        assert ProviderName.OPENROUTER in providers_found

    def test_list_anthropic_models(self) -> None:
        """Should return only Anthropic models when specified."""
        anthropic_models = list_models(ProviderName.ANTHROPIC)

        assert isinstance(anthropic_models, list)
        assert len(anthropic_models) >= 1
        assert all(m.provider == ProviderName.ANTHROPIC for m in anthropic_models)

    def test_list_openai_models(self) -> None:
        """Should return only OpenAI models."""
        openai_models = list_models(ProviderName.OPENAI)

        assert all(m.provider == ProviderName.OPENAI for m in openai_models)

    def test_list_google_models(self) -> None:
        """Should return only Google models."""
        google_models = list_models(ProviderName.GOOGLE)

        assert all(m.provider == ProviderName.GOOGLE for m in google_models)

    def test_list_mock_models_returns_empty(self) -> None:
        """Mock provider should have no models."""
        mock_models = list_models(ProviderName.MOCK)

        assert mock_models == []


class TestValidateModelCapability:
    """Test validate_model_capability() function."""

    def test_anthropic_haiku_supports_tool_use(self) -> None:
        """Anthropic Haiku should support tool_use capability."""
        result = validate_model_capability(
            ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001", "tool_use"
        )

        assert result is True

    def test_anthropic_haiku_supports_vision(self) -> None:
        """Anthropic Haiku should support vision capability."""
        result = validate_model_capability(
            ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001", "vision"
        )

        assert result is True

    def test_capability_not_supported_returns_false(self) -> None:
        """Should return False for unsupported capability."""
        result = validate_model_capability(
            ProviderName.ANTHROPIC,
            "claude-haiku-4-5-20251001",
            "nonexistent_capability",
        )

        assert result is False

    def test_invalid_model_raises_error(self) -> None:
        """Should raise ValueError for invalid model."""
        with pytest.raises(ValueError):
            validate_model_capability(ProviderName.ANTHROPIC, "invalid-model", "tool_use")

    def test_invalid_provider_raises_error(self) -> None:
        """Should raise ValueError for invalid provider."""
        with pytest.raises(ValueError):
            validate_model_capability("invalid", "model", "capability")  # type: ignore


class TestModelMetadata:
    """Test model metadata fields are populated correctly."""

    def test_anthropic_haiku_metadata(self) -> None:
        """Anthropic Haiku should have complete metadata."""
        config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")

        assert config.release_date == date(2025, 10, 1)
        assert config.is_deprecated is False
        assert config.deprecation_date is None
        assert config.cost_per_1k_input_tokens == 0.001
        assert config.cost_per_1k_output_tokens == 0.005
        assert "comparison" in config.recommended_for
        assert len(config.notes) > 0

    def test_anthropic_haiku_capabilities(self) -> None:
        """Anthropic Haiku should have correct capabilities."""
        config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")

        assert config.capabilities["tool_use"] is True
        assert config.capabilities["vision"] is True
        assert config.capabilities["function_calling"] is True
        assert config.capabilities["json_mode"] is True

    def test_anthropic_haiku_context_window(self) -> None:
        """Anthropic Haiku should have 200K context window."""
        config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")

        assert config.context_window == 200_000
        assert config.max_tokens == 64_000
        assert config.supports_streaming is True
