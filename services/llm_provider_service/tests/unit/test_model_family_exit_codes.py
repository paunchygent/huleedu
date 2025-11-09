"""Tests for family-aware exit code determination logic.

These tests verify that the CLI exit code determination correctly prioritizes
different types of model changes based on family-aware filtering:

Priority Order:
1. BREAKING_CHANGES (3): API incompatibilities requiring manual intervention
2. IN_FAMILY_UPDATES (4): New variants in tracked families (actionable)
3. UNTRACKED_FAMILIES (5): New families detected (informational)
4. UP_TO_DATE (0): No changes

Test Coverage:
- Exit code selection based on comparison results
- Priority order when multiple conditions exist
- Edge cases (empty results, multiple providers, etc.)
"""

from __future__ import annotations

import pytest

from services.llm_provider_service.cli_check_models import (
    ExitCode,
    determine_exit_code,
)
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestExitCodeDetermination:
    """Tests for exit code logic with family filtering."""

    @pytest.fixture
    def mock_tracked_model(self) -> DiscoveredModel:
        """Mock model in tracked family."""
        return DiscoveredModel(
            model_id="gpt-5-turbo",
            display_name="GPT-5 Turbo",
        )

    @pytest.fixture
    def mock_untracked_model(self) -> DiscoveredModel:
        """Mock model in untracked family."""
        return DiscoveredModel(
            model_id="dall-e-3",
            display_name="DALL-E 3",
        )

    def test_exit_code_up_to_date_when_no_changes(self) -> None:
        """Exit code 0 when manifest is up-to-date.

        If there are no new models, no deprecated models, no updates,
        and no breaking changes, the CLI should exit with code 0.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=True,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.UP_TO_DATE
        assert exit_code.value == 0

    def test_exit_code_in_family_updates_when_tracked_models_exist(
        self,
        mock_tracked_model: DiscoveredModel,
    ) -> None:
        """Exit code 4 when in-family updates exist.

        New models within tracked families are actionable and should
        trigger exit code 4 (IN_FAMILY_UPDATES).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[mock_tracked_model],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.IN_FAMILY_UPDATES
        assert exit_code.value == 4

    def test_exit_code_untracked_families_when_only_untracked_models_exist(
        self,
        mock_untracked_model: DiscoveredModel,
    ) -> None:
        """Exit code 5 when only untracked families exist.

        New models from untracked families are informational and should
        trigger exit code 5 (UNTRACKED_FAMILIES).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[mock_untracked_model],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.UNTRACKED_FAMILIES
        assert exit_code.value == 5

    def test_exit_code_breaking_changes_highest_priority(
        self,
        mock_tracked_model: DiscoveredModel,
    ) -> None:
        """Breaking changes take priority over in-family updates.

        If both breaking changes and in-family updates exist,
        exit code should be 3 (BREAKING_CHANGES).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[mock_tracked_model],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=["API version changed"],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.BREAKING_CHANGES
        assert exit_code.value == 3

    def test_exit_code_priority_in_family_over_untracked(
        self,
        mock_tracked_model: DiscoveredModel,
        mock_untracked_model: DiscoveredModel,
    ) -> None:
        """In-family updates take priority over untracked families.

        If both tracked and untracked family changes exist,
        exit code should be 4 (IN_FAMILY_UPDATES).
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[mock_tracked_model],
            new_untracked_families=[mock_untracked_model],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.IN_FAMILY_UPDATES
        assert exit_code.value == 4

    def test_exit_code_with_multiple_providers_takes_highest_priority(
        self,
        mock_tracked_model: DiscoveredModel,
        mock_untracked_model: DiscoveredModel,
    ) -> None:
        """When checking multiple providers, highest priority wins.

        If one provider has breaking changes and another has only
        in-family updates, the overall exit code should be 3.
        """
        result_breaking = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=["API version changed"],
            is_up_to_date=False,
        )

        result_in_family = ModelComparisonResult(
            provider=ProviderName.ANTHROPIC,
            new_models_in_tracked_families=[mock_tracked_model],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result_breaking, result_in_family])
        assert exit_code == ExitCode.BREAKING_CHANGES
        assert exit_code.value == 3

    def test_exit_code_deprecated_models_do_not_trigger_warning(self) -> None:
        """Deprecated models alone don't trigger non-zero exit code.

        Deprecated models are informational and don't require action,
        so they shouldn't change the exit code from UP_TO_DATE.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=["gpt-4-0314"],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,  # Note: is_up_to_date is False due to changes
        )

        # Despite is_up_to_date=False, exit code should still be 0
        # because deprecated models don't require action
        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.UP_TO_DATE
        assert exit_code.value == 0

    def test_exit_code_updated_models_do_not_trigger_warning(
        self,
        mock_tracked_model: DiscoveredModel,
    ) -> None:
        """Updated models alone don't trigger non-zero exit code.

        Model metadata updates are informational and don't require action,
        so they shouldn't change the exit code from UP_TO_DATE.
        """
        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[("gpt-5-2025-08-07", mock_tracked_model)],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.UP_TO_DATE
        assert exit_code.value == 0

    def test_exit_code_with_empty_results_list(self) -> None:
        """Empty results list returns UP_TO_DATE.

        If no providers were checked (empty list), the CLI should
        exit with code 0 as there's nothing to report.
        """
        exit_code = determine_exit_code([])
        assert exit_code == ExitCode.UP_TO_DATE
        assert exit_code.value == 0

    def test_exit_code_combines_results_from_all_providers(
        self,
        mock_tracked_model: DiscoveredModel,
        mock_untracked_model: DiscoveredModel,
    ) -> None:
        """Exit code considers all providers' results collectively.

        When checking multiple providers, the exit code should reflect
        the highest priority condition across all providers.
        """
        results = [
            ModelComparisonResult(
                provider=ProviderName.OPENAI,
                new_models_in_tracked_families=[],
                new_untracked_families=[mock_untracked_model],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=False,
            ),
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models_in_tracked_families=[mock_tracked_model],
                new_untracked_families=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=False,
            ),
        ]

        # ANTHROPIC has in-family updates (priority 2)
        # OPENAI has untracked families (priority 3)
        # Should return IN_FAMILY_UPDATES (higher priority)
        exit_code = determine_exit_code(results)
        assert exit_code == ExitCode.IN_FAMILY_UPDATES
        assert exit_code.value == 4


class TestExitCodePriorityLogic:
    """Tests specifically for exit code priority ordering."""

    def test_exit_code_priority_order_is_correct(self) -> None:
        """Verify exit code enum values follow priority order.

        Higher priority conditions should have higher numeric values
        (except UP_TO_DATE which is 0, and API_ERROR which is 2).
        """
        assert ExitCode.UP_TO_DATE.value == 0
        assert ExitCode.API_ERROR.value == 2
        assert ExitCode.BREAKING_CHANGES.value == 3
        assert ExitCode.IN_FAMILY_UPDATES.value == 4
        assert ExitCode.UNTRACKED_FAMILIES.value == 5

    def test_exit_code_all_four_conditions_breaking_wins(
        self,
    ) -> None:
        """When all four conditions exist, BREAKING_CHANGES wins.

        Test the full priority cascade: breaking > in-family > untracked > up-to-date.
        """
        tracked_model = DiscoveredModel(model_id="gpt-5-turbo", display_name="GPT-5 Turbo")
        untracked_model = DiscoveredModel(model_id="dall-e-3", display_name="DALL-E 3")

        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[tracked_model],
            new_untracked_families=[untracked_model],
            deprecated_models=["gpt-4-0314"],
            updated_models=[],
            breaking_changes=["API version changed"],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.BREAKING_CHANGES

    def test_exit_code_in_family_and_untracked_in_family_wins(self) -> None:
        """When in-family and untracked exist, IN_FAMILY_UPDATES wins."""
        tracked_model = DiscoveredModel(model_id="gpt-5-turbo", display_name="GPT-5 Turbo")
        untracked_model = DiscoveredModel(model_id="dall-e-3", display_name="DALL-E 3")

        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[tracked_model],
            new_untracked_families=[untracked_model],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        exit_code = determine_exit_code([result])
        assert exit_code == ExitCode.IN_FAMILY_UPDATES


class TestExitCodeEdgeCases:
    """Tests for edge cases in exit code determination."""

    def test_exit_code_with_all_providers_up_to_date(self) -> None:
        """When all providers are up-to-date, exit code is 0."""
        results = [
            ModelComparisonResult(
                provider=ProviderName.OPENAI,
                new_models_in_tracked_families=[],
                new_untracked_families=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=True,
            ),
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models_in_tracked_families=[],
                new_untracked_families=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=True,
            ),
        ]

        exit_code = determine_exit_code(results)
        assert exit_code == ExitCode.UP_TO_DATE

    def test_exit_code_is_deterministic(
        self,
    ) -> None:
        """Same input always produces same exit code (deterministic).

        Multiple calls with identical input must return identical exit codes
        to ensure reliable CI/CD integration.
        """
        tracked_model = DiscoveredModel(model_id="gpt-5-turbo", display_name="GPT-5 Turbo")

        result = ModelComparisonResult(
            provider=ProviderName.OPENAI,
            new_models_in_tracked_families=[tracked_model],
            new_untracked_families=[],
            deprecated_models=[],
            updated_models=[],
            breaking_changes=[],
            is_up_to_date=False,
        )

        # Call multiple times with same input
        exit_codes = [determine_exit_code([result]) for _ in range(5)]

        # All should be identical
        assert len(set(exit_codes)) == 1
        assert exit_codes[0] == ExitCode.IN_FAMILY_UPDATES

    def test_exit_code_enum_values_are_valid(self) -> None:
        """ExitCode enum values are valid shell exit codes.

        All enum values should be in range 0-255 for shell compatibility.
        """
        for exit_code in ExitCode:
            assert 0 <= exit_code.value <= 255, (
                f"Exit code {exit_code.name} has invalid value {exit_code.value}"
            )

    def test_exit_code_enum_has_all_required_values(self) -> None:
        """ExitCode enum contains all documented exit codes.

        Verify that all exit codes from the CLI docstring are present
        in the enum.
        """
        required_codes = {
            "UP_TO_DATE",
            "API_ERROR",
            "BREAKING_CHANGES",
            "IN_FAMILY_UPDATES",
            "UNTRACKED_FAMILIES",
        }

        enum_names = {code.name for code in ExitCode}
        assert required_codes == enum_names, (
            f"Missing exit codes: {required_codes - enum_names}"
        )
