"""Unit tests for model checker base protocol and models.

Tests cover:
- DiscoveredModel Pydantic validation
- ModelComparisonResult Pydantic validation
- Model immutability (frozen=True)
- Default value handling
- Field validation rules
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestDiscoveredModel:
    """Test DiscoveredModel Pydantic schema."""

    def test_required_fields_only(self) -> None:
        """DiscoveredModel should work with only required fields."""
        model = DiscoveredModel(
            model_id="test-model-123",
            display_name="Test Model",
        )

        assert model.model_id == "test-model-123"
        assert model.display_name == "Test Model"
        # Check defaults
        assert model.api_version is None
        assert model.capabilities == []
        assert model.max_tokens is None
        assert model.context_window is None
        assert model.supports_tool_use is False
        assert model.supports_streaming is True
        assert model.release_date is None
        assert model.is_deprecated is False
        assert model.deprecation_date is None
        assert model.notes == ""

    def test_all_fields_populated(self) -> None:
        """DiscoveredModel should accept all fields."""
        model = DiscoveredModel(
            model_id="claude-3-5-haiku-20241022",
            display_name="Claude 3.5 Haiku",
            api_version="2023-06-01",
            capabilities=["tool_use", "vision"],
            max_tokens=8192,
            context_window=200_000,
            supports_tool_use=True,
            supports_streaming=True,
            release_date=date(2024, 10, 22),
            is_deprecated=False,
            deprecation_date=None,
            notes="Latest Haiku model",
        )

        assert model.model_id == "claude-3-5-haiku-20241022"
        assert model.display_name == "Claude 3.5 Haiku"
        assert model.api_version == "2023-06-01"
        assert model.capabilities == ["tool_use", "vision"]
        assert model.max_tokens == 8192
        assert model.context_window == 200_000
        assert model.supports_tool_use is True
        assert model.supports_streaming is True
        assert model.release_date == date(2024, 10, 22)
        assert model.is_deprecated is False
        assert model.deprecation_date is None
        assert model.notes == "Latest Haiku model"

    def test_frozen_model_prevents_mutation(self) -> None:
        """DiscoveredModel should be immutable (frozen=True)."""
        model = DiscoveredModel(
            model_id="test-model",
            display_name="Test",
        )

        with pytest.raises(ValidationError, match="frozen"):
            model.model_id = "modified"  # type: ignore

    def test_missing_required_fields_raises_error(self) -> None:
        """DiscoveredModel should require model_id and display_name."""
        with pytest.raises(ValidationError, match="model_id"):
            DiscoveredModel(display_name="Test")  # type: ignore

        with pytest.raises(ValidationError, match="display_name"):
            DiscoveredModel(model_id="test")  # type: ignore

    @pytest.mark.parametrize(
        "field,value,expected",
        [
            # Empty lists should be allowed
            ("capabilities", [], []),
            # Empty strings should be allowed
            ("notes", "", ""),
            ("api_version", "", ""),
            # None values for optional fields
            ("api_version", None, None),
            ("max_tokens", None, None),
            ("context_window", None, None),
            ("release_date", None, None),
            ("deprecation_date", None, None),
            # Boolean defaults
            ("supports_tool_use", False, False),
            ("supports_streaming", True, True),
            ("is_deprecated", False, False),
        ],
    )
    def test_field_default_values(
        self,
        field: str,
        value: object,
        expected: object,
    ) -> None:
        """Test default values for optional fields."""
        model = DiscoveredModel(
            model_id="test",
            display_name="Test",
            **{field: value},  # type: ignore
        )

        assert getattr(model, field) == expected

    def test_deprecated_model_with_date(self) -> None:
        """Deprecated model should allow deprecation_date."""
        model = DiscoveredModel(
            model_id="legacy-model",
            display_name="Legacy Model",
            is_deprecated=True,
            deprecation_date=date(2024, 1, 1),
        )

        assert model.is_deprecated is True
        assert model.deprecation_date == date(2024, 1, 1)

    def test_capabilities_as_empty_list(self) -> None:
        """Capabilities should default to empty list."""
        model = DiscoveredModel(
            model_id="test",
            display_name="Test",
        )

        assert model.capabilities == []
        assert isinstance(model.capabilities, list)


class TestModelComparisonResult:
    """Test ModelComparisonResult Pydantic schema."""

    def test_required_fields_only(self) -> None:
        """ModelComparisonResult should work with only required fields."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            is_up_to_date=True,
        )

        assert result.provider == ProviderName.ANTHROPIC
        assert result.is_up_to_date is True
        # Check default factories
        assert result.new_models == []
        assert result.deprecated_models == []
        assert result.updated_models == []
        assert result.breaking_changes == []
        # Check checked_at defaults to today
        assert result.checked_at == date.today()

    def test_all_fields_populated(self) -> None:
        """ModelComparisonResult should accept all fields."""
        new_model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models=[new_model],
            deprecated_models=["old-model-123"],
            updated_models=[("updated-model", new_model)],
            breaking_changes=["API version changed from v1 to v2"],
            is_up_to_date=False,
            checked_at=date(2024, 11, 8),
        )

        assert result.provider == ProviderName.ANTHROPIC
        assert len(result.new_models) == 1
        assert result.new_models[0].model_id == "new-model"
        assert result.deprecated_models == ["old-model-123"]
        assert len(result.updated_models) == 1
        assert result.updated_models[0][0] == "updated-model"
        assert result.breaking_changes == ["API version changed from v1 to v2"]
        assert result.is_up_to_date is False
        assert result.checked_at == date(2024, 11, 8)

    def test_frozen_model_prevents_mutation(self) -> None:
        """ModelComparisonResult should be immutable (frozen=True)."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            is_up_to_date=True,
        )

        with pytest.raises(ValidationError, match="frozen"):
            result.is_up_to_date = False  # type: ignore

    def test_missing_required_fields_raises_error(self) -> None:
        """ModelComparisonResult should require provider and is_up_to_date."""
        with pytest.raises(ValidationError, match="provider"):
            ModelComparisonResult(is_up_to_date=True)  # type: ignore

        with pytest.raises(ValidationError, match="is_up_to_date"):
            ModelComparisonResult(provider=ProviderName.ANTHROPIC)  # type: ignore

    def test_is_up_to_date_logic_no_changes(self) -> None:
        """is_up_to_date should be True when no changes detected."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        assert result.is_up_to_date is True

    def test_is_up_to_date_logic_with_new_models(self) -> None:
        """is_up_to_date should be False when new models detected."""
        new_model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models=[new_model],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        assert result.is_up_to_date is False

    def test_is_up_to_date_logic_with_breaking_changes(self) -> None:
        """is_up_to_date should be False when breaking changes detected."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=["API version changed"],
            is_up_to_date=False,
        )

        assert result.is_up_to_date is False

    def test_empty_lists_initialize_correctly(self) -> None:
        """Default factory lists should initialize as empty."""
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            is_up_to_date=True,
        )

        # Verify all lists are empty but distinct instances
        assert result.new_models == []
        assert result.deprecated_models == []
        assert result.updated_models == []
        assert result.breaking_changes == []

        # Verify they're independent instances
        assert id(result.new_models) != id(result.deprecated_models)

    @pytest.mark.parametrize(
        "provider",
        [
            ProviderName.ANTHROPIC,
            ProviderName.OPENAI,
            ProviderName.GOOGLE,
            ProviderName.OPENROUTER,
            ProviderName.MOCK,
        ],
    )
    def test_all_providers_supported(self, provider: ProviderName) -> None:
        """ModelComparisonResult should work with all provider types."""
        result = ModelComparisonResult(
            provider=provider,
            is_up_to_date=True,
        )

        assert result.provider == provider

    def test_checked_at_defaults_to_today(self) -> None:
        """checked_at should default to today's date."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            is_up_to_date=True,
        )

        assert result.checked_at == date.today()

    def test_multiple_new_models(self) -> None:
        """ModelComparisonResult should handle multiple new models."""
        models = [
            DiscoveredModel(model_id=f"model-{i}", display_name=f"Model {i}") for i in range(5)
        ]

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models=models,
            is_up_to_date=False,
        )

        assert len(result.new_models) == 5
        assert all(isinstance(m, DiscoveredModel) for m in result.new_models)

    def test_multiple_updated_models(self) -> None:
        """ModelComparisonResult should handle multiple updated models."""
        model = DiscoveredModel(
            model_id="updated",
            display_name="Updated",
        )

        updated = [
            ("model-1", model),
            ("model-2", model),
            ("model-3", model),
        ]

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            updated_models=updated,
            is_up_to_date=False,
        )

        assert len(result.updated_models) == 3
        assert all(isinstance(t, tuple) for t in result.updated_models)
        assert all(isinstance(t[0], str) for t in result.updated_models)
        assert all(isinstance(t[1], DiscoveredModel) for t in result.updated_models)
