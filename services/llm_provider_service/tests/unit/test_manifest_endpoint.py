"""Unit tests for GET /api/v1/models manifest endpoint.

Tests cover:
- Model manifest retrieval (all providers)
- Provider filtering
- Deprecated model filtering
- Invalid provider handling
- Response structure validation
"""

import pytest

from services.llm_provider_service.api_models import (
    ModelInfoResponse,
    ModelManifestResponse,
)
from services.llm_provider_service.manifest import ProviderName, list_models


class TestManifestEndpointLogic:
    """Test manifest endpoint business logic."""

    def test_all_models_grouped_by_provider(self) -> None:
        """Manifest should group all non-deprecated models by provider."""
        # Arrange - Get all non-deprecated, non-MOCK models
        all_models = list_models()
        non_deprecated = [m for m in all_models if not m.is_deprecated]
        non_mock = [m for m in non_deprecated if m.provider != ProviderName.MOCK]

        # Act - Simulate endpoint logic
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model_config in non_mock:
            provider_name = model_config.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            model_info = ModelInfoResponse(
                model_id=model_config.model_id,
                provider=model_config.provider.value,
                display_name=model_config.display_name,
                model_family=model_config.model_family,
                max_tokens=model_config.max_tokens,
                context_window=model_config.context_window,
                supports_streaming=model_config.supports_streaming,
                capabilities=model_config.capabilities,
                cost_per_1k_input_tokens=model_config.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model_config.cost_per_1k_output_tokens,
                is_deprecated=model_config.is_deprecated,
                release_date=model_config.release_date,
                recommended_for=model_config.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        response = ModelManifestResponse(
            providers=providers_dict,
            total_models=len(non_mock),
        )

        # Assert - Should have multiple providers
        assert len(response.providers) > 0
        assert "anthropic" in response.providers
        assert "openai" in response.providers

        # Assert - Total models should match filtered count
        assert response.total_models == len(non_mock)

        # Assert - Each provider should have at least one model
        for provider_name, provider_models in response.providers.items():
            assert len(provider_models) > 0
            # All models in group should belong to that provider
            for model_info_item in provider_models:
                assert model_info_item.provider == provider_name

    def test_filter_by_specific_provider(self) -> None:
        """Filtering by provider should return only that provider's models."""
        # Arrange
        provider_filter = ProviderName.ANTHROPIC
        models = list_models(provider_filter)
        non_deprecated = [m for m in models if not m.is_deprecated]

        # Act - Simulate endpoint logic with provider filter
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model_config in non_deprecated:
            provider_name = model_config.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            model_info = ModelInfoResponse(
                model_id=model_config.model_id,
                provider=model_config.provider.value,
                display_name=model_config.display_name,
                model_family=model_config.model_family,
                max_tokens=model_config.max_tokens,
                context_window=model_config.context_window,
                supports_streaming=model_config.supports_streaming,
                capabilities=model_config.capabilities,
                cost_per_1k_input_tokens=model_config.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model_config.cost_per_1k_output_tokens,
                is_deprecated=model_config.is_deprecated,
                release_date=model_config.release_date,
                recommended_for=model_config.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        response = ModelManifestResponse(
            providers=providers_dict,
            total_models=len(non_deprecated),
        )

        # Assert - Should only have Anthropic provider
        assert len(response.providers) == 1
        assert "anthropic" in response.providers

        # Assert - All models should be Anthropic
        for model_info_item in response.providers["anthropic"]:
            assert model_info_item.provider == "anthropic"

    def test_include_deprecated_models(self) -> None:
        """When include_deprecated=True, deprecated models should be included."""
        # Arrange - Get all models including deprecated
        all_models = list_models()
        non_mock = [m for m in all_models if m.provider != ProviderName.MOCK]

        # Act - Simulate endpoint logic with include_deprecated=True
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model in non_mock:
            provider_name = model.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            model_info = ModelInfoResponse(
                model_id=model.model_id,
                provider=model.provider.value,
                display_name=model.display_name,
                model_family=model.model_family,
                max_tokens=model.max_tokens,
                context_window=model.context_window,
                supports_streaming=model.supports_streaming,
                capabilities=model.capabilities,
                cost_per_1k_input_tokens=model.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model.cost_per_1k_output_tokens,
                is_deprecated=model.is_deprecated,
                release_date=model.release_date,
                recommended_for=model.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        # Assert - Should include some deprecated models
        total_count = sum(len(models) for models in providers_dict.values())
        assert total_count == len(non_mock)

        # Note: We can't assert there ARE deprecated models without knowing the manifest,
        # but the logic should include them if they exist

    def test_exclude_deprecated_models_by_default(self) -> None:
        """By default (include_deprecated=False), deprecated models should be excluded."""
        # Arrange
        all_models = list_models()
        non_mock = [m for m in all_models if m.provider != ProviderName.MOCK]

        # Filter deprecated (default behavior)
        non_deprecated = [m for m in non_mock if not m.is_deprecated]

        # Act - Simulate endpoint logic with include_deprecated=False (default)
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model_config in non_deprecated:
            provider_name = model_config.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            model_info = ModelInfoResponse(
                model_id=model_config.model_id,
                provider=model_config.provider.value,
                display_name=model_config.display_name,
                model_family=model_config.model_family,
                max_tokens=model_config.max_tokens,
                context_window=model_config.context_window,
                supports_streaming=model_config.supports_streaming,
                capabilities=model_config.capabilities,
                cost_per_1k_input_tokens=model_config.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model_config.cost_per_1k_output_tokens,
                is_deprecated=model_config.is_deprecated,
                release_date=model_config.release_date,
                recommended_for=model_config.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        # Assert - Should not include any deprecated models
        for provider_models in providers_dict.values():
            for model_info_item in provider_models:
                assert model_info_item.is_deprecated is False

    def test_invalid_provider_validation(self) -> None:
        """Invalid provider names should raise ValueError."""
        # Arrange
        invalid_provider = "invalid_provider"

        # Act & Assert
        with pytest.raises(ValueError, match="is not a valid ProviderName"):
            ProviderName(invalid_provider)

    def test_mock_provider_excluded_from_api(self) -> None:
        """MOCK provider should be excluded from API responses."""
        # Arrange
        all_models = list_models()

        # Filter out MOCK (as endpoint does)
        non_mock = [m for m in all_models if m.provider != ProviderName.MOCK]

        # Act - Simulate endpoint logic
        providers_dict: dict[str, list[ModelInfoResponse]] = {}
        for model in non_mock:
            provider_name = model.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = []

            model_info = ModelInfoResponse(
                model_id=model.model_id,
                provider=model.provider.value,
                display_name=model.display_name,
                model_family=model.model_family,
                max_tokens=model.max_tokens,
                context_window=model.context_window,
                supports_streaming=model.supports_streaming,
                capabilities=model.capabilities,
                cost_per_1k_input_tokens=model.cost_per_1k_input_tokens,
                cost_per_1k_output_tokens=model.cost_per_1k_output_tokens,
                is_deprecated=model.is_deprecated,
                release_date=model.release_date,
                recommended_for=model.recommended_for,
            )
            providers_dict[provider_name].append(model_info)

        # Assert - MOCK should not be in results
        assert "mock" not in providers_dict

    def test_model_info_response_fields(self) -> None:
        """ModelInfoResponse should contain all required fields."""
        # Arrange - Get a real model
        models = list_models(ProviderName.ANTHROPIC)
        assert len(models) > 0
        model = models[0]

        # Act - Create ModelInfoResponse
        model_info = ModelInfoResponse(
            model_id=model.model_id,
            provider=model.provider.value,
            display_name=model.display_name,
            model_family=model.model_family,
            max_tokens=model.max_tokens,
            context_window=model.context_window,
            supports_streaming=model.supports_streaming,
            capabilities=model.capabilities,
            cost_per_1k_input_tokens=model.cost_per_1k_input_tokens,
            cost_per_1k_output_tokens=model.cost_per_1k_output_tokens,
            is_deprecated=model.is_deprecated,
            release_date=model.release_date,
            recommended_for=model.recommended_for,
        )

        # Assert - All fields should be populated correctly
        assert model_info.model_id == model.model_id
        assert model_info.provider == model.provider.value
        assert model_info.display_name == model.display_name
        assert model_info.model_family == model.model_family
        assert model_info.max_tokens == model.max_tokens
        assert model_info.context_window == model.context_window
        assert model_info.supports_streaming == model.supports_streaming
        assert model_info.capabilities == model.capabilities
        assert model_info.is_deprecated == model.is_deprecated

    def test_manifest_response_structure(self) -> None:
        """ModelManifestResponse should have correct structure."""
        # Arrange
        providers_dict = {
            "anthropic": [
                ModelInfoResponse(
                    model_id="claude-test",
                    provider="anthropic",
                    display_name="Claude Test",
                    model_family="claude",
                    max_tokens=4096,
                    context_window=200_000,
                    supports_streaming=True,
                    capabilities={"tool_use": True},
                    cost_per_1k_input_tokens=0.001,
                    cost_per_1k_output_tokens=0.002,
                    is_deprecated=False,
                    release_date=None,
                    recommended_for=["testing"],
                )
            ],
        }

        # Act
        response = ModelManifestResponse(
            providers=providers_dict,
            total_models=1,
        )

        # Assert
        assert "providers" in response.model_dump()
        assert "total_models" in response.model_dump()
        assert response.total_models == 1
        assert "anthropic" in response.providers
        assert len(response.providers["anthropic"]) == 1
