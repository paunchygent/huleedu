"""Compatibility report generation for LLM model version checking.

This module generates JSON and markdown reports from model compatibility checks.
Reports are used for:
- CI/CD pipeline validation
- Manual review workflows
- Change tracking and auditing
- Decision support for model updates

The reports provide:
- Current model status and compatibility
- Newly discovered models with recommendations
- Breaking changes and migration requirements
- Structured data for automated processing (JSON)
- Human-readable summaries (markdown)

Usage:
    from services.llm_provider_service.compatibility_reporter import CompatibilityReporter
    from services.llm_provider_service.model_checker.anthropic_checker import (
        AnthropicModelChecker,
    )

    checker = AnthropicModelChecker(client=client, logger=logger)
    result = await checker.compare_with_manifest()

    reporter = CompatibilityReporter()
    json_report = reporter.generate_json_report(result)
    markdown_report = reporter.generate_markdown_report(result)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import (
    SUPPORTED_MODELS,
    get_model_config,
)


class CompatibilityReporter:
    """Generate compatibility reports from model comparison results.

    This reporter converts ModelComparisonResult objects into structured
    JSON reports and human-readable markdown summaries. The reports follow
    a standardized schema for consistent processing across different providers.
    """

    def generate_json_report(self, result: ModelComparisonResult) -> str:
        """Generate JSON compatibility report.

        Args:
            result: Model comparison result to report on

        Returns:
            JSON string with structured compatibility data

        Format:
            {
                "check_date": "2025-11-09T02:30:00Z",
                "provider": "anthropic",
                "current_model": {
                    "model_id": "claude-3-5-haiku-20241022",
                    "status": "compatible",
                    "last_tested": "2025-11-09T02:30:00Z"
                },
                "discovered_models": [
                    {
                        "model_id": "claude-3-5-sonnet-20241022",
                        "compatibility_status": "unknown",
                        "issues": [],
                        "recommendation": "requires_testing"
                    }
                ],
                "breaking_changes": ["API version changed from..."]
            }
        """
        default_model_id = SUPPORTED_MODELS.default_models.get(result.provider)
        current_default = (
            get_model_config(result.provider, default_model_id) if default_model_id else None
        )

        # Combine both tracked and untracked families for reporting
        all_new_models = result.new_models_in_tracked_families + result.new_untracked_families

        report: dict[str, Any] = {
            "check_date": datetime.now().isoformat() + "Z",
            "provider": result.provider.value,
            "current_model": self._format_current_model(
                current_default.model_id if current_default else None,
                result,
            ),
            "discovered_models": [
                self._format_discovered_model(model) for model in all_new_models
            ],
            "breaking_changes": result.breaking_changes,
            "is_up_to_date": result.is_up_to_date,
            "checked_at": result.checked_at.isoformat(),
        }

        return json.dumps(report, indent=2)

    def generate_markdown_report(self, result: ModelComparisonResult) -> str:
        """Generate human-readable markdown compatibility report.

        Args:
            result: Model comparison result to report on

        Returns:
            Markdown formatted report string

        Example Output:
            # LLM Model Compatibility Report

            **Provider**: Anthropic
            **Check Date**: 2025-11-09 02:30:00 UTC
            **Status**: ✅ Up to date

            ## Current Model

            - **Model ID**: `claude-3-5-haiku-20241022`
            - **Status**: Compatible
            - **Last Tested**: 2025-11-09 02:30:00 UTC

            ## New Models Discovered

            ### claude-3-5-sonnet-20241022
            - **Display Name**: Claude 3.5 Sonnet
            - **Recommendation**: Requires compatibility testing
            - **Capabilities**: tool_use, vision, function_calling
        """
        default_model_id = SUPPORTED_MODELS.default_models.get(result.provider)
        current_default = (
            get_model_config(result.provider, default_model_id) if default_model_id else None
        )

        lines: list[str] = [
            "# LLM Model Compatibility Report",
            "",
            f"**Provider**: {result.provider.value.title()}",
            f"**Check Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Status**: {'✅ Up to date' if result.is_up_to_date else '⚠️ Changes detected'}",
            "",
        ]

        # Current model section
        lines.extend(
            [
                "## Current Model",
                "",
            ]
        )

        if current_default:
            lines.extend(
                [
                    f"- **Model ID**: `{current_default.model_id}`",
                    f"- **Display Name**: {current_default.display_name}",
                    "- **Status**: Compatible (in manifest)",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "- **Status**: No default model configured in manifest",
                    "",
                ]
            )

        # New models section (combine tracked and untracked families)
        all_new_models = result.new_models_in_tracked_families + result.new_untracked_families
        if all_new_models:
            lines.extend(
                [
                    "## New Models Discovered",
                    "",
                ]
            )

            for model in all_new_models:
                lines.extend(self._format_model_markdown(model))

        # Deprecated models section
        if result.deprecated_models:
            lines.extend(
                [
                    "## Deprecated Models",
                    "",
                    "The following models in the manifest are deprecated:",
                    "",
                ]
            )

            for model_id in result.deprecated_models:
                lines.append(f"- `{model_id}`")

            lines.append("")

        # Updated models section
        if result.updated_models:
            lines.extend(
                [
                    "## Updated Models",
                    "",
                    "The following models have metadata changes:",
                    "",
                ]
            )

            for model_id, discovered in result.updated_models:
                lines.extend(
                    [
                        f"### {model_id}",
                        f"- **Display Name**: {discovered.display_name}",
                        "- **Status**: Metadata updated",
                        "",
                    ]
                )

        # Breaking changes section
        if result.breaking_changes:
            lines.extend(
                [
                    "## ⚠️ Breaking Changes",
                    "",
                    "**ACTION REQUIRED**: The following breaking changes were detected:",
                    "",
                ]
            )

            for change in result.breaking_changes:
                lines.append(f"- {change}")

            lines.append("")

        # Recommendations section
        lines.extend(
            [
                "## Recommendations",
                "",
            ]
        )

        if result.is_up_to_date:
            lines.append("✅ No action required. Manifest is up to date.")
        else:
            lines.append("📋 Review the changes above and:")
            lines.append("")

            all_new_models = result.new_models_in_tracked_families + result.new_untracked_families
            if all_new_models:
                lines.append("1. Run compatibility tests for new models:")
                lines.append("   ```bash")
                lines.append(
                    "   CHECK_NEW_MODELS=1 pdm run pytest-root "
                    "services/llm_provider_service/tests/integration/test_model_compatibility.py -v"
                )
                lines.append("   ```")
                lines.append("")

            if result.deprecated_models:
                lines.append("2. Update manifest to remove deprecated models")
                lines.append("")

            if result.breaking_changes:
                lines.append("3. Review breaking changes and update implementations")
                lines.append("")

        return "\n".join(lines)

    def _format_current_model(
        self,
        model_id: str | None,
        result: ModelComparisonResult,
    ) -> dict[str, Any]:
        """Format current model information for JSON report.

        Args:
            model_id: Current default model ID from manifest
            result: Comparison result

        Returns:
            Dictionary with current model status
        """
        if not model_id:
            return {
                "model_id": None,
                "status": "not_configured",
                "last_tested": None,
            }

        # Check if current model is deprecated
        is_deprecated = model_id in result.deprecated_models

        return {
            "model_id": model_id,
            "status": "deprecated" if is_deprecated else "compatible",
            "last_tested": datetime.now().isoformat() + "Z",
        }

    def _format_discovered_model(self, model: DiscoveredModel) -> dict[str, Any]:
        """Format discovered model for JSON report.

        Args:
            model: Discovered model to format

        Returns:
            Dictionary with model information and recommendations
        """
        # Determine recommendation based on model characteristics
        recommendation = self._get_recommendation(model)

        issues: list[str] = []
        if model.is_deprecated:
            issues.append("Model is marked as deprecated by provider")

        return {
            "model_id": model.model_id,
            "display_name": model.display_name,
            "compatibility_status": "unknown",  # Requires actual testing
            "issues": issues,
            "recommendation": recommendation,
            "capabilities": model.capabilities,
            "max_tokens": model.max_tokens,
            "supports_tool_use": model.supports_tool_use,
            "release_date": model.release_date.isoformat() if model.release_date else None,
            "is_deprecated": model.is_deprecated,
        }

    def _get_recommendation(self, model: DiscoveredModel) -> str:
        """Determine upgrade recommendation for a discovered model.

        Args:
            model: Discovered model

        Returns:
            Recommendation string: safe_upgrade, requires_testing, or not_recommended
        """
        if model.is_deprecated:
            return "not_recommended"

        # If model supports required capabilities, recommend testing
        required_capabilities = {"tool_use", "function_calling"}
        model_caps = set(model.capabilities)

        if required_capabilities.intersection(model_caps):
            return "requires_testing"

        # Unknown capabilities or missing required features
        return "requires_testing"

    def _format_model_markdown(self, model: DiscoveredModel) -> list[str]:
        """Format discovered model as markdown section.

        Args:
            model: Discovered model to format

        Returns:
            List of markdown lines
        """
        lines = [
            f"### {model.model_id}",
            f"- **Display Name**: {model.display_name}",
        ]

        if model.capabilities:
            caps_str = ", ".join(model.capabilities[:5])
            lines.append(f"- **Capabilities**: {caps_str}")

        if model.max_tokens:
            lines.append(f"- **Max Tokens**: {model.max_tokens:,}")

        if model.context_window:
            lines.append(f"- **Context Window**: {model.context_window:,}")

        if model.release_date:
            lines.append(f"- **Release Date**: {model.release_date}")

        recommendation = self._get_recommendation(model)
        rec_emoji = {
            "safe_upgrade": "✅",
            "requires_testing": "⚠️",
            "not_recommended": "❌",
        }.get(recommendation, "⚠️")

        rec_text = recommendation.replace("_", " ").title()
        lines.append(f"- **Recommendation**: {rec_emoji} {rec_text}")

        if model.is_deprecated:
            lines.append("- **Status**: ⚠️ Deprecated by provider")

        if model.notes:
            lines.append(f"- **Notes**: {model.notes}")

        lines.append("")

        return lines
