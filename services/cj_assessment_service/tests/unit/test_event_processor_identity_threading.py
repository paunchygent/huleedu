"""Unit tests for identity threading in CJ Assessment event processor.

This module tests the identity threading behavior in event_processor.py,
focusing on user_id/org_id extraction from ELS_CJAssessmentRequestV1 events
and their proper inclusion in converted_request_data passed to workflows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.models.error_models import ErrorDetail

from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

PROMPT_TEXT = "Prompt text for CJ assessment."
ESSAY_TEXT = "Sample essay content for testing."
DEFAULT_INSTRUCTIONS = "Compare the quality of these essays."


class TestEventProcessorIdentityThreading:
    """Tests for identity threading behavior in CJ Assessment event processor."""

    @pytest.fixture
    def mock_cj_repository(self) -> Any:
        """Create mock CJ repository with required methods."""
        from services.cj_assessment_service.tests.unit.mocks import MockDatabase

        return MockDatabase()

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client."""
        client = AsyncMock(spec=ContentClientProtocol)

        async def fetch_effect(storage_id: str, correlation_id: Any) -> str:
            if "prompt" in storage_id:
                return PROMPT_TEXT
            return ESSAY_TEXT

        client.fetch_content = AsyncMock(side_effect=fetch_effect)
        return client

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_failed = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_llm_interaction(self) -> AsyncMock:
        """Create mock LLM interaction service."""
        llm = AsyncMock(spec=LLMInteractionProtocol)
        return llm

    @pytest.fixture
    def mock_workflow_function(self, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        """Mock the run_cj_assessment_workflow function."""
        workflow_mock = AsyncMock()
        workflow_mock.return_value = Mock(rankings=[], batch_id=12345)
        monkeypatch.setattr(
            "services.cj_assessment_service.event_processor.run_cj_assessment_workflow",
            workflow_mock,
        )
        return workflow_mock

    @pytest.fixture
    def test_settings(self) -> Mock:
        """Create test settings."""
        return Mock(
            MAX_PAIRWISE_COMPARISONS=100,
            CJ_ASSESSMENT_FAILED_TOPIC="cj_assessment.failed.v1",
            SERVICE_NAME="cj_assessment_service",
        )

    def create_kafka_message(self, envelope_data: dict[str, Any]) -> ConsumerRecord:
        """Create a ConsumerRecord for testing."""
        import json

        json_bytes = json.dumps(envelope_data).encode("utf-8")
        return ConsumerRecord(
            topic="test-topic",
            partition=0,
            offset=0,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
            timestamp_type=0,
            key=None,
            value=json_bytes,
            checksum=None,
            serialized_key_size=len(json_bytes),
            serialized_value_size=len(json_bytes),
            headers=[],
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, expected_user_id, expected_org_id",
        [
            # Standard identity threading with both fields present
            ("user-123", "org-456", "user-123", "org-456"),
            # Only user_id present (common case)
            ("user-789", None, "user-789", None),
            # Swedish characters in identity fields (domain requirement)
            ("användar-åäö", "organisation-ÅÄÖ", "användar-åäö", "organisation-ÅÄÖ"),
            # Empty string handling (edge case)
            ("", "", "", ""),
            # Long identity strings (boundary condition)
            ("u" * 200, "o" * 200, "u" * 200, "o" * 200),
        ],
    )
    async def test_identity_extraction_from_els_event(
        self,
        user_id: str | None,
        org_id: str | None,
        expected_user_id: str | None,
        expected_org_id: str | None,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test identity extraction from ELS_CJAssessmentRequestV1 events.

        Verifies that user_id and org_id are correctly extracted from the event
        and passed through to the workflow function in converted_request_data.
        """
        # Arrange - Override identity fields in test data
        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": user_id, "org_id": org_id}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert - Verify workflow was called with correct identity data
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args
        converted_request_data = call_args.kwargs["request_data"]

        assert converted_request_data["user_id"] == expected_user_id
        assert converted_request_data["org_id"] == expected_org_id
        assert converted_request_data["student_prompt_text"] == PROMPT_TEXT
        assert (
            converted_request_data["student_prompt_storage_id"]
            == "prompt-storage-with-overrides"
        )

        mock_content_client.fetch_content.assert_any_await(
            "prompt-storage-with-overrides", envelope.correlation_id
        )

    @pytest.mark.asyncio
    async def test_converted_request_data_structure_completeness(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that converted_request_data contains all required fields including identities.

        Verifies the complete structure of the converted request data dict passed to workflows,
        ensuring identity fields are properly included alongside other required data.
        """
        # Arrange
        test_user_id = "comprehensive-test-user"
        test_org_id = "comprehensive-test-org"

        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": test_user_id, "org_id": test_org_id}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert - Verify complete converted_request_data structure
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args
        converted_request_data = call_args.kwargs["request_data"]

        # Check all required fields are present
        required_fields = [
            "bos_batch_id",
            "essays_to_process",
            "language",
            "course_code",
            "student_prompt_text",
            "student_prompt_storage_id",
            "llm_config_overrides",
            "user_id",
            "org_id",
        ]

        for field in required_fields:
            assert field in converted_request_data, f"Missing required field: {field}"

        # Verify identity fields have expected values
        assert converted_request_data["user_id"] == test_user_id
        assert converted_request_data["org_id"] == test_org_id

        # Verify other fields maintain correct types and values
        assert isinstance(converted_request_data["bos_batch_id"], str)
        assert isinstance(converted_request_data["essays_to_process"], list)
        assert len(converted_request_data["essays_to_process"]) > 0
        assert converted_request_data["language"] == event_data.language
        assert converted_request_data["course_code"] == event_data.course_code
        assert converted_request_data["student_prompt_text"] == PROMPT_TEXT
        assert (
            converted_request_data["student_prompt_storage_id"]
            == "prompt-storage-with-overrides"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, should_process_normally",
        [
            # Normal case with both identities
            ("valid-user", "valid-org", True),
            # Missing org_id should still process (common case)
            ("valid-user", None, True),
            # Edge case: empty user_id (but still valid string)
            ("", "valid-org", True),
            # Edge case: empty strings for both
            ("", "", True),
        ],
    )
    async def test_missing_identity_handling(
        self,
        user_id: str,
        org_id: str | None,
        should_process_normally: bool,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test behavior with edge case identity field values.

        Verifies that empty user_id or missing org_id fields do not cause processing
        to fail at the event processor level. Note: user_id is required by the API contract.
        """
        # Arrange
        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": user_id, "org_id": org_id}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        result = await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert
        if should_process_normally:
            assert result is True
            mock_workflow_function.assert_called_once()

            # Verify identity values are passed through as-is (including None)
            call_args = mock_workflow_function.call_args
            converted_request_data = call_args.kwargs["request_data"]
            assert converted_request_data["user_id"] == user_id
            assert converted_request_data["org_id"] == org_id
            assert converted_request_data["student_prompt_text"] == PROMPT_TEXT

    @pytest.mark.asyncio
    async def test_prompt_fetch_failure_records_metric(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ensure prompt fetch failures increment the dedicated metric."""

        error_detail = ErrorDetail(
            error_code=ErrorCode.CONTENT_SERVICE_ERROR,
            message="Prompt fetch failed",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="cj_assessment_service",
            operation="fetch_content",
            details={},
        )
        mock_content_client.fetch_content = AsyncMock(
            side_effect=[HuleEduError(error_detail), ESSAY_TEXT, ESSAY_TEXT]
        )

        prompt_counter = MagicMock()
        label_mock = MagicMock()
        prompt_counter.labels.return_value = label_mock

        monkeypatch.setattr(
            "services.cj_assessment_service.event_processor.get_business_metrics",
            lambda: {
                "cj_comparisons_made": None,
                "cj_assessment_duration_seconds": None,
                "kafka_queue_latency_seconds": None,
                "prompt_fetch_failures": prompt_counter,
            },
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=cj_assessment_request_data_with_overrides,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        label_mock.inc.assert_called_once()
        prompt_counter.labels.assert_called_with(reason="content_service_error")

        mock_workflow_function.assert_called_once()
        converted_request_data = mock_workflow_function.call_args.kwargs["request_data"]
        assert converted_request_data["student_prompt_text"] is None
        assert (
            converted_request_data["student_prompt_storage_id"]
            == "prompt-storage-with-overrides"
        )

    @pytest.mark.asyncio
    async def test_correlation_id_preservation_with_identities(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that correlation_id is preserved through workflow calls with identity data.

        Verifies that trace context (correlation_id) is maintained throughout the
        processing pipeline when identity fields are present.
        """
        # Arrange
        test_correlation_id = uuid4()
        test_user_id = "trace-test-user"
        test_org_id = "trace-test-org"

        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": test_user_id, "org_id": test_org_id}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=test_correlation_id,
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert - Verify correlation_id is passed to workflow
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Verify identity data is also preserved alongside trace context
        converted_request_data = call_args.kwargs["request_data"]
        assert converted_request_data["user_id"] == test_user_id
        assert converted_request_data["org_id"] == test_org_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "special_characters, expected_preserved",
        [
            # Swedish vowels (critical for domain)
            ("åäöÅÄÖ", True),
            # Unicode normalization test
            ("café", True),
            # Special characters in user context
            ("user@domain.com", True),
            # Hyphenated organization names
            ("multi-part-org-name", True),
            # Numbers in identities
            ("user123", True),
            # Mixed case preservation
            ("MixedCaseUser", True),
        ],
    )
    async def test_swedish_characters_in_identity_fields(
        self,
        special_characters: str,
        expected_preserved: bool,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test handling of Swedish characters and special characters in identity fields.

        Verifies that identity fields containing Swedish characters (åäöÅÄÖ) and
        other special characters are preserved correctly through the processing pipeline.
        """
        # Arrange - Create identities with special characters
        user_id_with_special = f"user-{special_characters}"
        org_id_with_special = f"org-{special_characters}"

        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": user_id_with_special, "org_id": org_id_with_special}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert - Verify special characters are preserved
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args
        converted_request_data = call_args.kwargs["request_data"]

        if expected_preserved:
            assert converted_request_data["user_id"] == user_id_with_special
            assert converted_request_data["org_id"] == org_id_with_special

            # Verify exact character preservation
            assert special_characters in converted_request_data["user_id"]
            assert special_characters in converted_request_data["org_id"]

    @pytest.mark.asyncio
    async def test_identity_threading_with_multiple_essays(
        self,
        cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test identity threading with multiple essays in the batch.

        Verifies that identity fields are correctly handled when processing
        batches containing multiple essays for comparison.
        """
        # Arrange - Use fixture that has multiple essays and different identity setup
        # cj_assessment_request_data_no_overrides has user_id but no org_id
        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=cj_assessment_request_data_no_overrides,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args
        converted_request_data = call_args.kwargs["request_data"]

        # Verify identity fields are present and match fixture values
        assert converted_request_data["user_id"] == "test-user-456"
        assert converted_request_data["org_id"] is None

        # Verify essays were processed correctly
        assert "essays_to_process" in converted_request_data
        essays = converted_request_data["essays_to_process"]
        assert len(essays) == 2  # Fixture has 2 essays

        # Verify essay structure is correct
        for essay in essays:
            assert "els_essay_id" in essay
            assert "text_storage_id" in essay

    @pytest.mark.asyncio
    async def test_workflow_call_parameters_with_identity_data(
        self,
        cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
        mock_cj_repository: Any,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_workflow_function: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that workflow function receives all required parameters including identity context.

        Verifies that the run_cj_assessment_workflow function is called with all
        required parameters and that identity data is properly included.
        """
        # Arrange
        test_user_id = "workflow-param-test-user"
        test_org_id = "workflow-param-test-org"
        test_correlation_id = uuid4()

        event_data = cj_assessment_request_data_with_overrides.model_copy(
            update={"user_id": test_user_id, "org_id": test_org_id}
        )

        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=test_correlation_id,
            data=event_data,
        )

        kafka_msg = self.create_kafka_message(envelope.model_dump(mode="json"))

        # Act
        await process_single_message(
            msg=kafka_msg,
            database=mock_cj_repository,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=test_settings,
        )

        # Assert - Verify all workflow parameters
        mock_workflow_function.assert_called_once()
        call_args = mock_workflow_function.call_args

        # Check positional parameters are correct
        assert call_args.kwargs["database"] == mock_cj_repository
        assert call_args.kwargs["content_client"] == mock_content_client
        assert call_args.kwargs["llm_interaction"] == mock_llm_interaction
        assert call_args.kwargs["event_publisher"] == mock_event_publisher
        assert call_args.kwargs["settings"] == test_settings
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Check request_data parameter includes identity fields
        request_data = call_args.kwargs["request_data"]
        assert request_data["user_id"] == test_user_id
        assert request_data["org_id"] == test_org_id
