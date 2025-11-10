"""Unit tests for compatibility report generation.

Tests cover:
- JSON report format and structure
- Markdown report format and structure
- Current model status formatting
- Discovered model recommendations
- Breaking changes display
- Report generation with empty results
- Report generation with multiple models
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from services.llm_provider_service.compatibility_reporter import CompatibilityReporter
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestCompatibilityReporterJSON:
    """Test JSON report generation."""

    def test_json_report_with_up_to_date_manifest(self) -> None:
        """JSON report should show up-to-date status when no changes detected."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        assert report["provider"] == "anthropic"
        assert report["is_up_to_date"] is True
        assert report["discovered_models"] == []
        assert report["breaking_changes"] == []
        assert report["checked_at"] == "2025-11-09"

    def test_json_report_with_new_models(self) -> None:
        """JSON report should list new models with recommendations."""
        new_model = DiscoveredModel(
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            capabilities=["tool_use", "vision"],
            max_tokens=8192,
            supports_tool_use=True,
            release_date=date(2024, 10, 22),
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[new_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        assert report["is_up_to_date"] is False
        assert len(report["discovered_models"]) == 1

        discovered = report["discovered_models"][0]
        assert discovered["model_id"] == "claude-3-5-sonnet-20241022"
        assert discovered["display_name"] == "Claude 3.5 Sonnet"
        assert discovered["compatibility_status"] == "unknown"
        assert discovered["recommendation"] == "requires_testing"
        assert discovered["capabilities"] == ["tool_use", "vision"]
        assert discovered["max_tokens"] == 8192
        assert discovered["supports_tool_use"] is True
        assert discovered["is_deprecated"] is False
        assert discovered["release_date"] == "2024-10-22"

    def test_json_report_with_deprecated_model(self) -> None:
        """JSON report should mark deprecated models as not_recommended."""
        deprecated_model = DiscoveredModel(
            model_id="claude-2-deprecated",
            display_name="Claude 2 (Deprecated)",
            is_deprecated=True,
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[deprecated_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        discovered = report["discovered_models"][0]
        assert discovered["is_deprecated"] is True
        assert discovered["recommendation"] == "not_recommended"
        assert "deprecated by provider" in discovered["issues"][0]

    def test_json_report_with_breaking_changes(self) -> None:
        """JSON report should include breaking changes list."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[
                "API version changed from 2023-01-01 to 2024-01-01",
                "Structured output method changed from json to tool_use",
            ],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        assert len(report["breaking_changes"]) == 2
        assert "API version changed" in report["breaking_changes"][0]
        assert "Structured output method changed" in report["breaking_changes"][1]

    def test_json_report_current_model_when_not_configured(self) -> None:
        """JSON report should handle missing default model gracefully."""
        # Use MOCK provider which has no default model
        result = ModelComparisonResult(
            provider=ProviderName.MOCK,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        assert report["current_model"]["model_id"] is None
        assert report["current_model"]["status"] == "not_configured"
        assert report["current_model"]["last_tested"] is None

    def test_json_report_current_model_when_deprecated(self) -> None:
        """JSON report should mark current model as deprecated if in deprecated list."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=["claude-haiku-4-5-20251001"],  # Current default
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        json_output = reporter.generate_json_report(result)
        report = json.loads(json_output)

        assert report["current_model"]["model_id"] == "claude-haiku-4-5-20251001"
        assert report["current_model"]["status"] == "deprecated"


class TestCompatibilityReporterMarkdown:
    """Test markdown report generation."""

    def test_markdown_report_structure(self) -> None:
        """Markdown report should have proper heading structure."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "# LLM Model Compatibility Report" in markdown
        assert "**Provider**: Anthropic" in markdown
        assert "**Status**: ✅ Up to date" in markdown
        assert "## Current Model" in markdown
        assert "## Recommendations" in markdown

    def test_markdown_report_with_new_models(self) -> None:
        """Markdown report should format new models with details."""
        new_model = DiscoveredModel(
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            capabilities=["tool_use", "vision", "function_calling"],
            max_tokens=8192,
            context_window=200_000,
            release_date=date(2024, 10, 22),
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[new_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "## New Models Discovered" in markdown
        assert "### claude-3-5-sonnet-20241022" in markdown
        assert "Claude 3.5 Sonnet" in markdown
        assert "tool_use, vision, function_calling" in markdown
        assert "8,192" in markdown
        assert "200,000" in markdown
        assert "2024-10-22" in markdown
        assert "⚠️ Requires Testing" in markdown

    def test_markdown_report_with_deprecated_models(self) -> None:
        """Markdown report should list deprecated models."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=["claude-2-old", "claude-instant-deprecated"],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "## Deprecated Models" in markdown
        assert "`claude-2-old`" in markdown
        assert "`claude-instant-deprecated`" in markdown

    def test_markdown_report_with_breaking_changes(self) -> None:
        """Markdown report should highlight breaking changes."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[
                "API version changed from 2023-01-01 to 2024-01-01",
                "Default model changed from haiku to sonnet",
            ],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "## ⚠️ Breaking Changes" in markdown
        assert "**ACTION REQUIRED**" in markdown
        assert "API version changed" in markdown
        assert "Default model changed" in markdown

    def test_markdown_report_recommendations_when_up_to_date(self) -> None:
        """Markdown report should show no action when up to date."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "✅ No action required" in markdown

    def test_markdown_report_recommendations_with_new_models(self) -> None:
        """Markdown report should suggest testing for new models."""
        new_model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
        )

        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[new_model],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "Run compatibility tests for new models" in markdown
        assert "CHECK_NEW_MODELS=1" in markdown
        assert "test_model_compatibility.py" in markdown

    def test_markdown_report_recommendations_with_deprecated_models(self) -> None:
        """Markdown report should suggest manifest update for deprecated models."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=["old-model"],
            breaking_changes=[],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "Update manifest to remove deprecated models" in markdown

    def test_markdown_report_recommendations_with_breaking_changes(self) -> None:
        """Markdown report should prioritize breaking changes."""
        result = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            breaking_changes=["Critical API change"],
            is_up_to_date=False,
            checked_at=date(2025, 11, 9),
        )

        reporter = CompatibilityReporter()
        markdown = reporter.generate_markdown_report(result)

        assert "Review breaking changes and update implementations" in markdown


class TestRecommendationLogic:
    """Test recommendation generation logic."""

    def test_recommendation_for_deprecated_model(self) -> None:
        """Deprecated models should get not_recommended."""
        reporter = CompatibilityReporter()

        deprecated_model = DiscoveredModel(
            model_id="old-model",
            display_name="Old Model",
            is_deprecated=True,
        )

        recommendation = reporter._get_recommendation(deprecated_model)
        assert recommendation == "not_recommended"

    def test_recommendation_for_model_with_tool_use(self) -> None:
        """Models with tool_use capability should get requires_testing."""
        reporter = CompatibilityReporter()

        model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
            capabilities=["tool_use", "vision"],
        )

        recommendation = reporter._get_recommendation(model)
        assert recommendation == "requires_testing"

    def test_recommendation_for_model_with_function_calling(self) -> None:
        """Models with function_calling capability should get requires_testing."""
        reporter = CompatibilityReporter()

        model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
            capabilities=["function_calling"],
        )

        recommendation = reporter._get_recommendation(model)
        assert recommendation == "requires_testing"

    def test_recommendation_for_model_without_required_capabilities(self) -> None:
        """Models without tool capabilities should get requires_testing."""
        reporter = CompatibilityReporter()

        model = DiscoveredModel(
            model_id="basic-model",
            display_name="Basic Model",
            capabilities=["vision"],
        )

        recommendation = reporter._get_recommendation(model)
        assert recommendation == "requires_testing"
