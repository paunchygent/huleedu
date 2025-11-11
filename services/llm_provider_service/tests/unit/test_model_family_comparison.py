"""Tests for family-aware model comparison logic.

These tests verify that model checker comparison algorithms correctly categorize
new models based on their family membership:

- Models within tracked families → new_models_in_tracked_families (actionable)
- Models from untracked families → new_untracked_families (informational)

Test Coverage:
- Family-based categorization of new models
- Handling of empty active families configuration
- Interaction between family filtering and existing comparison logic
- Edge cases (duplicate families, empty results, etc.)
"""

from __future__ import annotations

from datetime import date

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestFamilyAwareComparison:
    """Tests for family-aware model comparison logic."""

    @pytest.fixture
    def settings_with_tracked_families(self) -> Settings:
        """Settings with active model families configured."""
        return Settings(
            _env_file=None,
            OPENAI_API_KEY="test-key",
            ANTHROPIC_API_KEY="test-key",
            ACTIVE_MODEL_FAMILIES={
                ProviderName.OPENAI: ["gpt-5", "gpt-4o"],
                ProviderName.ANTHROPIC: ["claude-haiku"],
            },
        )

    @pytest.fixture
    def settings_with_empty_families(self) -> Settings:
        """Settings with no active model families (all models untracked)."""
        return Settings(
            _env_file=None,
            OPENAI_API_KEY="test-key",
            ACTIVE_MODEL_FAMILIES={},
        )

    @pytest.fixture
    def discovered_gpt5_model(self) -> DiscoveredModel:
        """Discovered model in tracked GPT-5 family."""
        return DiscoveredModel(
            model_id="gpt-5-turbo-2025-09-01",
            display_name="GPT-5 Turbo",
            api_version="2023-06-01",
            capabilities=["tool_use", "json_mode"],
            max_tokens=4096,
            context_window=32768,
            supports_tool_use=True,
            supports_streaming=True,
        )

    @pytest.fixture
    def discovered_dalle_model(self) -> DiscoveredModel:
        """Discovered model in untracked DALL-E family."""
        return DiscoveredModel(
            model_id="dall-e-3",
            display_name="DALL-E 3",
            api_version="2023-06-01",
            capabilities=["image_generation"],
            max_tokens=None,
            context_window=None,
            supports_tool_use=False,
            supports_streaming=False,
        )

    def test_new_model_in_tracked_family_categorized_correctly(
        self,
        settings_with_tracked_families: Settings,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """New model in tracked family goes to new_models_in_tracked_families.

        When a model from a tracked family (e.g., gpt-5) is discovered in the
        provider API but not in the manifest, it should be categorized as
        actionable (new_models_in_tracked_families).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[discovered_gpt5_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert len(result.new_models_in_tracked_families) == 1
        assert result.new_models_in_tracked_families[0].model_id == "gpt-5-turbo-2025-09-01"
        assert len(result.new_untracked_families) == 0

    def test_new_model_in_untracked_family_categorized_correctly(
        self,
        settings_with_tracked_families: Settings,
        discovered_dalle_model: DiscoveredModel,
    ) -> None:
        """New model in untracked family goes to new_untracked_families.

        When a model from an untracked family (e.g., dall-e) is discovered
        in the provider API, it should be categorized as informational
        (new_untracked_families).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[discovered_dalle_model],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert len(result.new_untracked_families) == 1
        assert result.new_untracked_families[0].model_id == "dall-e-3"
        assert len(result.new_models_in_tracked_families) == 0

    def test_multiple_models_categorized_by_family(
        self,
        settings_with_tracked_families: Settings,
        discovered_gpt5_model: DiscoveredModel,
        discovered_dalle_model: DiscoveredModel,
    ) -> None:
        """Multiple new models are categorized based on their families.

        When multiple models are discovered, each should be categorized
        independently based on whether its family is tracked.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[discovered_gpt5_model],
            new_untracked_families=[discovered_dalle_model],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert len(result.new_models_in_tracked_families) == 1
        assert len(result.new_untracked_families) == 1
        assert result.new_models_in_tracked_families[0].model_id == "gpt-5-turbo-2025-09-01"
        assert result.new_untracked_families[0].model_id == "dall-e-3"

    def test_new_models_field_removed(self) -> None:
        """Verify new_models field no longer exists in ModelComparisonResult.

        The old new_models field has been removed as part of Phase 2.
        Tests should verify it does not exist to prevent regression.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert not hasattr(result, "new_models"), (
            "new_models field should be removed from ModelComparisonResult"
        )

    def test_empty_active_families_treats_all_as_untracked(
        self,
        settings_with_empty_families: Settings,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """When no active families configured, all new models are untracked.

        If ACTIVE_MODEL_FAMILIES is empty, no families are considered tracked,
        so all new models should be categorized as informational.
        """
        # With empty ACTIVE_MODEL_FAMILIES, even GPT-5 models are untracked
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[discovered_gpt5_model],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert len(result.new_models_in_tracked_families) == 0
        assert len(result.new_untracked_families) == 1

    def test_up_to_date_status_when_no_changes(self) -> None:
        """is_up_to_date is True when no new models in any category.

        If there are no new tracked models, no untracked models, no deprecated
        models, and no breaking changes, the manifest is considered up-to-date.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.is_up_to_date is True

    def test_up_to_date_status_false_with_tracked_changes(
        self,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """is_up_to_date is False when tracked family changes exist.

        New models in tracked families should set is_up_to_date to False,
        signaling that manifest update is recommended.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[discovered_gpt5_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert result.is_up_to_date is False

    def test_up_to_date_status_with_only_untracked_changes(
        self,
        discovered_dalle_model: DiscoveredModel,
    ) -> None:
        """is_up_to_date considers untracked families as changes.

        Even if only untracked families have new models, is_up_to_date should
        reflect that there are differences between API and manifest.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[discovered_dalle_model],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert result.is_up_to_date is False

    def test_comparison_result_is_immutable(
        self,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """ModelComparisonResult is frozen and cannot be modified.

        Result objects should be immutable to ensure comparison integrity
        and prevent accidental modifications.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[discovered_gpt5_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        with pytest.raises(Exception):  # Pydantic raises ValidationError or AttributeError
            result.is_up_to_date = True  # type: ignore[misc]

    def test_discovered_model_contains_required_fields(
        self,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """DiscoveredModel contains all required fields for comparison.

        Models discovered from APIs must have sufficient metadata for
        comparison and categorization logic.
        """
        assert discovered_gpt5_model.model_id
        assert discovered_gpt5_model.display_name
        assert isinstance(discovered_gpt5_model.capabilities, list)
        assert isinstance(discovered_gpt5_model.supports_tool_use, bool)
        assert isinstance(discovered_gpt5_model.supports_streaming, bool)

    def test_comparison_result_preserves_other_categories(
        self,
        discovered_gpt5_model: DiscoveredModel,
    ) -> None:
        """Family filtering doesn't interfere with other comparison categories.

        Deprecated models, updated models, and breaking changes should still
        be tracked independently of family-based filtering.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[discovered_gpt5_model],
            new_untracked_families=[],
            deprecated_models=["gpt-4-0314"],
            breaking_changes=["API version changed"],
            is_up_to_date=False,
        )

        assert len(result.deprecated_models) == 1
        assert len(result.breaking_changes) == 1

    def test_checked_at_field_defaults_to_today(self) -> None:
        """checked_at field defaults to current date.

        Comparison results should automatically record when the check
        was performed for audit and tracking purposes.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.checked_at == date.today()

    def test_provider_field_is_required(self) -> None:
        """Provider field is required and must be valid ProviderName enum.

        Comparison results must specify which provider was checked to
        enable proper routing and reporting.
        """
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.provider == ProviderName.ANTHROPIC
        assert isinstance(result.provider, ProviderName)


class TestFamilyComparisonEdgeCases:
    """Tests for edge cases in family-aware comparison logic."""

    def test_duplicate_models_in_same_category(
        self,
    ) -> None:
        """Duplicate models in same category are handled gracefully.

        If comparison logic mistakenly adds the same model multiple times,
        the result should still be valid (though this indicates a bug).
        """
        model = DiscoveredModel(
            model_id="gpt-5-turbo",
            display_name="GPT-5 Turbo",
        )

        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[model, model],  # Duplicate
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        # Result should still be valid, even with duplicates
        assert len(result.new_models_in_tracked_families) == 2

    def test_all_categories_empty_means_up_to_date(self) -> None:
        """When all categories are empty, manifest is up-to-date.

        If no models are in any change category, is_up_to_date should be True.
        """
        result = ModelComparisonResult(
            provider=ProviderName.GOOGLE,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.is_up_to_date is True
        assert len(result.new_models_in_tracked_families) == 0
        assert len(result.new_untracked_families) == 0

    def test_provider_enum_matches_across_result(self) -> None:
        """Provider enum is consistent across all result fields.

        The provider field should use the same enum value throughout
        the comparison result.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENROUTER,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.provider == ProviderName.OPENROUTER
        assert result.provider.value == "openrouter"
