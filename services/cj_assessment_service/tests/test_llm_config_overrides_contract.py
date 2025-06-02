"""
Contract compliance tests for LLM Config Overrides.

These tests verify that the LLM configuration overrides functionality
properly validates, serializes, and deserializes event contracts.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from common_core.events.cj_assessment_events import (
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope


class TestLLMConfigOverridesContract:
    """Test the LLMConfigOverrides Pydantic model contract."""

    def test_llm_config_overrides_full_model(self) -> None:
        """Test LLMConfigOverrides with all fields."""
        # Arrange & Act
        overrides = LLMConfigOverrides(
            model_override="gpt-4o",
            temperature_override=0.3,
            max_tokens_override=2000,
            provider_override="openai"
        )

        # Assert
        assert overrides.model_override == "gpt-4o"
        assert overrides.temperature_override == 0.3
        assert overrides.max_tokens_override == 2000
        assert overrides.provider_override == "openai"

    def test_llm_config_overrides_minimal_model(self) -> None:
        """Test LLMConfigOverrides with only model override."""
        # Arrange & Act
        overrides = LLMConfigOverrides(
            model_override="claude-3-sonnet-20240229"
        )

        # Assert
        assert overrides.model_override == "claude-3-sonnet-20240229"
        assert overrides.temperature_override is None
        assert overrides.max_tokens_override is None
        assert overrides.provider_override is None

    def test_llm_config_overrides_empty_model(self) -> None:
        """Test LLMConfigOverrides with no overrides."""
        # Arrange & Act
        overrides = LLMConfigOverrides()

        # Assert
        assert overrides.model_override is None
        assert overrides.temperature_override is None
        assert overrides.max_tokens_override is None
        assert overrides.provider_override is None

    def test_llm_config_overrides_temperature_validation(self) -> None:
        """Test temperature validation constraints."""
        # Valid temperature range
        valid_temps = [0.0, 0.5, 1.0, 1.5, 2.0]
        for temp in valid_temps:
            overrides = LLMConfigOverrides(temperature_override=temp)
            assert overrides.temperature_override == temp

        # Invalid temperatures
        invalid_temps = [-0.1, 2.1, -1.0, 3.0]
        for temp in invalid_temps:
            with pytest.raises(ValidationError):
                LLMConfigOverrides(temperature_override=temp)

    def test_llm_config_overrides_max_tokens_validation(self) -> None:
        """Test max_tokens validation constraints."""
        # Valid max_tokens
        valid_tokens = [1, 100, 1000, 8000]
        for tokens in valid_tokens:
            overrides = LLMConfigOverrides(max_tokens_override=tokens)
            assert overrides.max_tokens_override == tokens

        # Invalid max_tokens
        invalid_tokens = [0, -1, -100]
        for tokens in invalid_tokens:
            with pytest.raises(ValidationError):
                LLMConfigOverrides(max_tokens_override=tokens)

    def test_llm_config_overrides_serialization_roundtrip(self) -> None:
        """Test serialization and deserialization roundtrip."""
        # Arrange
        original = LLMConfigOverrides(
            model_override="gpt-4o",
            temperature_override=0.8,
            max_tokens_override=3000,
            provider_override="openai"
        )

        # Act - Serialize and deserialize
        serialized = original.model_dump(mode="json")
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        reconstructed = LLMConfigOverrides.model_validate(parsed)

        # Assert
        assert reconstructed.model_override == original.model_override
        assert reconstructed.temperature_override == original.temperature_override
        assert reconstructed.max_tokens_override == original.max_tokens_override
        assert reconstructed.provider_override == original.provider_override


class TestELSCJAssessmentRequestV1WithOverrides:
    """Test the updated ELS_CJAssessmentRequestV1 with LLM config overrides."""

    def test_request_with_llm_overrides(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        llm_config_overrides: LLMConfigOverrides,
    ) -> None:
        """Test request event with LLM config overrides."""
        # Assert
        assert cj_assessment_request_data_with_overrides.llm_config_overrides is not None
        assert cj_assessment_request_data_with_overrides.llm_config_overrides.model_override == "gpt-4o"
        assert cj_assessment_request_data_with_overrides.llm_config_overrides.temperature_override == 0.3
        assert cj_assessment_request_data_with_overrides.llm_config_overrides.max_tokens_override == 2000

    def test_request_without_llm_overrides(
        self,
        cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
    ) -> None:
        """Test request event without LLM config overrides."""
        # Assert
        assert cj_assessment_request_data_no_overrides.llm_config_overrides is None

    def test_request_serialization_with_overrides(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
    ) -> None:
        """Test serialization of request with LLM overrides."""
        # Act - Serialize and deserialize
        serialized = cj_assessment_request_data_with_overrides.model_dump(mode="json")
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        reconstructed = ELS_CJAssessmentRequestV1.model_validate(parsed)

        # Assert
        assert reconstructed.llm_config_overrides is not None
        assert reconstructed.llm_config_overrides.model_override == "gpt-4o"
        assert reconstructed.llm_config_overrides.temperature_override == 0.3
        assert reconstructed.llm_config_overrides.max_tokens_override == 2000

    def test_request_serialization_without_overrides(
        self,
        cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
    ) -> None:
        """Test serialization of request without LLM overrides."""
        # Act - Serialize and deserialize
        serialized = cj_assessment_request_data_no_overrides.model_dump(mode="json")
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        reconstructed = ELS_CJAssessmentRequestV1.model_validate(parsed)

        # Assert
        assert reconstructed.llm_config_overrides is None


class TestEventEnvelopeWithOverrides:
    """Test EventEnvelope serialization with LLM config overrides."""

    def test_envelope_serialization_with_overrides(
        self,
        cj_request_envelope_with_overrides: EventEnvelope[ELS_CJAssessmentRequestV1],
    ) -> None:
        """Test EventEnvelope serialization with LLM overrides."""
        # Act - Simulate Kafka serialization
        serialized = json.dumps(
            cj_request_envelope_with_overrides.model_dump(mode="json")
        ).encode("utf-8")
        parsed = json.loads(serialized.decode("utf-8"))
        reconstructed = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate(parsed)

        # Assert envelope structure
        assert reconstructed.event_type == "els.cj_assessment.requested.v1"
        assert reconstructed.source_service == "essay-lifecycle-service"
        assert reconstructed.correlation_id == cj_request_envelope_with_overrides.correlation_id

        # Assert data structure with overrides
        assert reconstructed.data.llm_config_overrides is not None
        assert reconstructed.data.llm_config_overrides.model_override == "gpt-4o"
        assert reconstructed.data.llm_config_overrides.temperature_override == 0.3
        assert reconstructed.data.llm_config_overrides.max_tokens_override == 2000

    def test_envelope_serialization_without_overrides(
        self,
        cj_request_envelope_no_overrides: EventEnvelope[ELS_CJAssessmentRequestV1],
    ) -> None:
        """Test EventEnvelope serialization without LLM overrides."""
        # Act - Simulate Kafka serialization
        serialized = json.dumps(
            cj_request_envelope_no_overrides.model_dump(mode="json")
        ).encode("utf-8")
        parsed = json.loads(serialized.decode("utf-8"))
        reconstructed = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate(parsed)

        # Assert envelope structure
        assert reconstructed.event_type == "els.cj_assessment.requested.v1"
        assert reconstructed.source_service == "essay-lifecycle-service"
        assert reconstructed.correlation_id == cj_request_envelope_no_overrides.correlation_id

        # Assert data structure without overrides
        assert reconstructed.data.llm_config_overrides is None
