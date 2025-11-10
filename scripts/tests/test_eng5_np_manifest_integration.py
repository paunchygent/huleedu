"""Integration tests for ENG5 batch runner manifest-based model validation.

This module verifies that the ENG5 batch runner correctly validates LLM model
selections against the model manifest before publishing events to Kafka.

Test Coverage:
- validate_llm_overrides() accepts valid manifest models
- validate_llm_overrides() rejects invalid model IDs
- Validation error messages suggest llm-check-models command
- _build_llm_overrides() creates correct LLMConfigOverrides structure
- Event composition includes llm_config_overrides field
- Validation skips when no model specified
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from common_core import LLMProviderType
from common_core.domain_enums import CourseCode, Language
from common_core.events.cj_assessment_events import LLMConfigOverrides
from common_core.metadata_models import EssayProcessingInputRefV1

from scripts.cj_experiments_runners.eng5_np.cli import (
    _build_llm_overrides,
    validate_llm_overrides,
)
from scripts.cj_experiments_runners.eng5_np.requests import compose_cj_assessment_request
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings
from services.llm_provider_service.model_manifest import (
    ModelConfig,
    ProviderName,
    StructuredOutputMethod,
)


class TestValidateLLMOverrides:
    """Test suite for validate_llm_overrides() function."""

    def test_validate_accepts_valid_manifest_model(self) -> None:
        """Verify validation passes for models that exist in manifest."""
        # Create a mock ModelConfig that will be returned by get_model_config
        mock_config = ModelConfig(
            model_id="claude-haiku-4-5-20251001",
            provider=ProviderName.ANTHROPIC,
            display_name="Claude Haiku 4.5",
            model_family="claude-haiku",
            api_version="2023-06-01",
            structured_output_method=StructuredOutputMethod.TOOL_USE,
            max_tokens=64_000,
            release_date=None,
            is_deprecated=False,
        )

        mock_get_config = MagicMock(return_value=mock_config)
        with patch(
            "services.llm_provider_service.model_manifest.get_model_config",
            mock_get_config,
        ):
            # Should not raise exception
            validate_llm_overrides(provider="anthropic", model="claude-haiku-4-5-20251001")

        # Verify manifest was queried with correct parameters (behavioral verification)
        mock_get_config.assert_called_once_with(
            ProviderName.ANTHROPIC,
            "claude-haiku-4-5-20251001",
        )

    def test_validate_rejects_invalid_model_id(self) -> None:
        """Verify validation raises BadParameter for models not in manifest."""
        with patch(
            "services.llm_provider_service.model_manifest.get_model_config",
            side_effect=ValueError("Unknown model: anthropic/invalid-model-id"),
        ):
            with pytest.raises(typer.BadParameter) as exc_info:
                validate_llm_overrides(provider="anthropic", model="invalid-model-id")

            # Verify error message is helpful
            error_msg = str(exc_info.value)
            assert "invalid-model-id" in error_msg
            assert "not found in manifest" in error_msg
            assert "pdm run llm-check-models" in error_msg

    def test_validation_error_suggests_cli_command(self) -> None:
        """Verify error message suggests running llm-check-models command."""
        with patch(
            "services.llm_provider_service.model_manifest.get_model_config",
            side_effect=ValueError("Model not found"),
        ):
            with pytest.raises(typer.BadParameter) as exc_info:
                validate_llm_overrides(provider="anthropic", model="unknown-model")

            error_msg = str(exc_info.value)
            # Should suggest the CLI command for discovering models
            assert "pdm run llm-check-models --provider anthropic" in error_msg

    def test_validate_skips_when_no_model_specified(self) -> None:
        """Verify validation skips gracefully when model is None."""
        mock_get_config = MagicMock()
        with patch(
            "services.llm_provider_service.model_manifest.get_model_config",
            mock_get_config,
        ):
            # Should not raise exception
            validate_llm_overrides(provider=None, model=None)

        # Verify manifest was NOT queried (behavioral verification)
        mock_get_config.assert_not_called()

    def test_validate_handles_deprecated_model_warning(self) -> None:
        """Verify validation passes for deprecated models (warning is logged but no exception raised)."""
        mock_config = ModelConfig(
            model_id="claude-old-deprecated",
            provider=ProviderName.ANTHROPIC,
            display_name="Claude Old Deprecated",
            model_family="claude-haiku",
            api_version="2023-01-01",
            structured_output_method=StructuredOutputMethod.TOOL_USE,
            max_tokens=4096,
            release_date=None,
            is_deprecated=True,
            deprecation_date=None,
            notes="This model is deprecated. Use claude-3-5-haiku instead.",
        )

        mock_get_config = MagicMock(return_value=mock_config)
        with patch(
            "services.llm_provider_service.model_manifest.get_model_config",
            mock_get_config,
        ):
            # Should not raise exception even for deprecated models (behavioral verification)
            validate_llm_overrides(provider="anthropic", model="claude-old-deprecated")

        # Verify manifest was queried (deprecated models are still valid)
        mock_get_config.assert_called_once_with(
            ProviderName.ANTHROPIC,
            "claude-old-deprecated",
        )

    def test_validate_rejects_invalid_provider(self) -> None:
        """Verify validation raises BadParameter for invalid provider names."""
        with pytest.raises(typer.BadParameter) as exc_info:
            validate_llm_overrides(provider="invalid-provider", model="some-model")

        error_msg = str(exc_info.value)
        assert "Invalid provider" in error_msg
        assert "Valid providers:" in error_msg


class TestBuildLLMOverrides:
    """Test suite for _build_llm_overrides() function."""

    def test_build_creates_correct_structure(self) -> None:
        """Verify _build_llm_overrides creates valid LLMConfigOverrides."""
        result = _build_llm_overrides(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            temperature=0.3,
            max_tokens=2000,
        )

        assert result is not None
        assert isinstance(result, LLMConfigOverrides)
        assert result.provider_override == LLMProviderType.ANTHROPIC
        assert result.model_override == "claude-haiku-4-5-20251001"
        assert result.temperature_override == 0.3
        assert result.max_tokens_override == 2000

    def test_build_returns_none_when_no_overrides(self) -> None:
        """Verify _build_llm_overrides returns None when no parameters specified."""
        result = _build_llm_overrides(provider=None, model=None, temperature=None, max_tokens=None)

        assert result is None

    def test_build_handles_partial_overrides(self) -> None:
        """Verify _build_llm_overrides handles partial parameter sets."""
        # Only model specified
        result = _build_llm_overrides(
            provider=None, model="claude-haiku-4-5-20251001", temperature=None, max_tokens=None
        )

        assert result is not None
        assert result.model_override == "claude-haiku-4-5-20251001"
        assert result.provider_override is None
        assert result.temperature_override is None
        assert result.max_tokens_override is None

    def test_build_converts_provider_string_to_enum(self) -> None:
        """Verify provider string attempts enum conversion."""
        # Use lowercase "anthropic" which matches LLMProviderType enum value
        result = _build_llm_overrides(
            provider="anthropic", model="test-model", temperature=None, max_tokens=None
        )

        assert result is not None
        # Provider should be converted to enum when lowercase string matches
        assert result.provider_override == LLMProviderType.ANTHROPIC


class TestEventComposition:
    """Test suite for event composition with LLM overrides."""

    @pytest.fixture
    def sample_settings_with_overrides(self) -> RunnerSettings:
        """Create runner settings with LLM overrides."""
        return RunnerSettings(
            assignment_id=uuid.UUID(int=1),
            course_id=uuid.UUID(int=2),
            grade_scale="eng5_np_legacy_9_step",
            mode=RunnerMode.DRY_RUN,
            use_kafka=False,
            output_dir=Path("/tmp/output"),
            runner_version="0.1.0",
            git_sha="test-sha",
            batch_id="test-batch",
            user_id="test-user",
            org_id="test-org",
            course_code=CourseCode.ENG5,
            language=Language.ENGLISH,
            correlation_id=uuid.uuid4(),
            kafka_bootstrap="kafka:9092",
            kafka_client_id="test-client",
            content_service_url="http://localhost:8001/v1/content",
            llm_overrides=LLMConfigOverrides(
                provider_override=LLMProviderType.ANTHROPIC,
                model_override="claude-haiku-4-5-20251001",
                temperature_override=0.3,
                max_tokens_override=2000,
            ),
            await_completion=False,
            completion_timeout=1800.0,
        )

    @pytest.fixture
    def sample_essay_refs(self) -> list[EssayProcessingInputRefV1]:
        """Create sample essay references for testing."""
        return [
            EssayProcessingInputRefV1(
                essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())
            ),
            EssayProcessingInputRefV1(
                essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())
            ),
        ]

    def test_compose_event_includes_llm_overrides(
        self,
        sample_settings_with_overrides: RunnerSettings,
        sample_essay_refs: list[EssayProcessingInputRefV1],
    ) -> None:
        """Verify composed event includes llm_config_overrides field."""
        envelope = compose_cj_assessment_request(
            settings=sample_settings_with_overrides,
            essay_refs=sample_essay_refs,
            prompt_reference=None,
        )

        # Verify envelope structure
        assert envelope is not None
        assert envelope.data is not None

        # Verify LLM config overrides are included
        assert envelope.data.llm_config_overrides is not None
        assert envelope.data.llm_config_overrides.provider_override == LLMProviderType.ANTHROPIC
        assert envelope.data.llm_config_overrides.model_override == "claude-haiku-4-5-20251001"
        assert envelope.data.llm_config_overrides.temperature_override == 0.3
        assert envelope.data.llm_config_overrides.max_tokens_override == 2000

    def test_compose_event_without_overrides(
        self, sample_essay_refs: list[EssayProcessingInputRefV1]
    ) -> None:
        """Verify composed event handles None llm_config_overrides gracefully."""
        settings_no_overrides = RunnerSettings(
            assignment_id=uuid.UUID(int=1),
            course_id=uuid.UUID(int=2),
            grade_scale="eng5_np_legacy_9_step",
            mode=RunnerMode.DRY_RUN,
            use_kafka=False,
            output_dir=Path("/tmp/output"),
            runner_version="0.1.0",
            git_sha="test-sha",
            batch_id="test-batch",
            user_id="test-user",
            org_id=None,
            course_code=CourseCode.ENG5,
            language=Language.ENGLISH,
            correlation_id=uuid.uuid4(),
            kafka_bootstrap="kafka:9092",
            kafka_client_id="test-client",
            content_service_url="http://localhost:8001/v1/content",
            llm_overrides=None,  # No overrides
            await_completion=False,
            completion_timeout=1800.0,
        )

        envelope = compose_cj_assessment_request(
            settings=settings_no_overrides,
            essay_refs=sample_essay_refs,
            prompt_reference=None,
        )

        # Should still create valid envelope, with None overrides
        assert envelope is not None
        assert envelope.data is not None
        assert envelope.data.llm_config_overrides is None
