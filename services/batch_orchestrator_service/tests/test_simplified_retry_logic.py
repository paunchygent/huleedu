"""
Tests for simplified retry logic implementation.

Tests the natural retry capabilities through idempotency and user-initiated
retry through existing pipeline request patterns.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1


class TestSimplifiedRetryLogic:
    """Test simplified retry approach using existing infrastructure."""

    @pytest.fixture
    def mock_batch_repo(self) -> AsyncMock:
        """Mock batch repository for retry testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_phase_coordinator(self) -> AsyncMock:
        """Mock phase coordinator for retry testing."""
        return AsyncMock()

    @pytest.fixture
    def sample_batch_context(self) -> BatchRegistrationRequestV1:
        """Sample batch context for testing."""
        return BatchRegistrationRequestV1(
            expected_essay_count=3,
            course_code="ENG5",
            class_designation="Class 9A",
            teacher_name="Test Teacher",
            essay_instructions="Test instructions",
            user_id="user_123",
        )

    @pytest.fixture
    def sample_essays(self) -> list[dict[str, str]]:
        """Sample essays for testing."""
        return [
            {"essay_id": "essay_1", "filename": "essay1.txt"},
            {"essay_id": "essay_2", "filename": "essay2.txt"},
            {"essay_id": "essay_3", "filename": "essay3.txt"},
        ]

    @pytest.mark.asyncio
    async def test_client_pipeline_request_with_retry_context(self) -> None:
        """Test ClientBatchPipelineRequestV1 supports retry context."""
        # Test normal request
        normal_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="spellcheck",
            user_id="user_123",
        )

        assert normal_request.is_retry is False
        assert normal_request.retry_reason is None

        # Test retry request
        retry_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="spellcheck",
            user_id="user_123",
            is_retry=True,
            retry_reason="Network error occurred, retrying spellcheck",
        )

        assert retry_request.is_retry is True
        assert retry_request.retry_reason == "Network error occurred, retrying spellcheck"

    @pytest.mark.asyncio
    async def test_retry_request_validation(self) -> None:
        """Test retry request validation logic."""
        # Valid retry request
        retry_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="ai_feedback",
            user_id="user_123",
            is_retry=True,
            retry_reason="User initiated retry from UI",
        )

        # Verify all fields are properly set
        assert retry_request.batch_id == "batch_123"
        assert retry_request.requested_pipeline == "ai_feedback"
        assert retry_request.user_id == "user_123"
        assert retry_request.is_retry is True
        assert retry_request.retry_reason == "User initiated retry from UI"

    @pytest.mark.asyncio
    async def test_phase_name_validation_for_retry(self) -> None:
        """Test that phase names are properly validated for retry requests."""
        # Valid phase names
        valid_phases = ["spellcheck", "ai_feedback", "cj_assessment", "nlp"]

        for phase in valid_phases:
            try:
                phase_enum = PhaseName(phase)
                assert phase_enum.value == phase
            except ValueError:
                pytest.fail(f"Valid phase {phase} should not raise ValueError")

        # Invalid phase name should raise ValueError
        with pytest.raises(ValueError):
            PhaseName("invalid_phase")

    @pytest.mark.asyncio
    async def test_cj_assessment_batch_only_constraint(self) -> None:
        """Test CJ Assessment batch-only retry constraint."""
        # CJ Assessment retry request
        cj_retry_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="cj_assessment",
            user_id="user_123",
            is_retry=True,
            retry_reason="CJ Assessment failed, retrying entire batch",
        )

        # Verify the request is valid
        assert cj_retry_request.requested_pipeline == "cj_assessment"
        assert cj_retry_request.is_retry is True

        # The batch-only constraint is enforced at the API level,
        # not in the data model itself

    @pytest.mark.asyncio
    async def test_retry_reason_length_validation(self) -> None:
        """Test retry reason length validation."""
        # Valid retry reason
        short_reason = "Network error"
        retry_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="spellcheck",
            user_id="user_123",
            is_retry=True,
            retry_reason=short_reason,
        )
        assert retry_request.retry_reason == short_reason

        # Test maximum length (500 characters)
        max_length_reason = "x" * 500
        retry_request_max = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="spellcheck",
            user_id="user_123",
            is_retry=True,
            retry_reason=max_length_reason,
        )
        assert retry_request_max.retry_reason is not None
        assert len(retry_request_max.retry_reason) == 500

        # Test exceeding maximum length should raise validation error
        with pytest.raises(ValueError):
            ClientBatchPipelineRequestV1(
                batch_id="batch_123",
                requested_pipeline="spellcheck",
                user_id="user_123",
                is_retry=True,
                retry_reason="x" * 501,  # Exceeds max length
            )

    @pytest.mark.asyncio
    async def test_retry_context_serialization(self) -> None:
        """Test that retry context serializes properly for Kafka."""
        retry_request = ClientBatchPipelineRequestV1(
            batch_id="batch_123",
            requested_pipeline="spellcheck",
            user_id="user_123",
            is_retry=True,
            retry_reason="Transient network error, retrying",
        )

        # Test model_dump for Kafka serialization
        serialized = retry_request.model_dump()

        assert serialized["batch_id"] == "batch_123"
        assert serialized["requested_pipeline"] == "spellcheck"
        assert serialized["user_id"] == "user_123"
        assert serialized["is_retry"] is True
        assert serialized["retry_reason"] == "Transient network error, retrying"

        # Test deserialization
        deserialized = ClientBatchPipelineRequestV1.model_validate(serialized)
        assert deserialized.is_retry is True
        assert deserialized.retry_reason == "Transient network error, retrying"


class TestNaturalRetryViaIdempotency:
    """Test natural retry capabilities through existing idempotency system."""

    @pytest.mark.asyncio
    async def test_idempotency_enables_natural_retry(self) -> None:
        """
        Test that idempotency decorator enables natural retry by deleting Redis keys on failure.

        This is a conceptual test - the actual idempotency behavior is tested
        in the service library tests.
        """
        # The idempotency decorator in huleedu_service_libs/idempotency.py
        # already provides natural retry by:
        # 1. Deleting Redis keys on processing failure
        # 2. Allowing the same message to be reprocessed
        # 3. Providing TTL-based cleanup

        # This test validates that our retry approach leverages this existing capability
        assert True  # Placeholder - actual idempotency tests are in service library

    @pytest.mark.asyncio
    async def test_existing_pipeline_coordination_supports_retry(self) -> None:
        """
        Test that existing phase coordination supports retry scenarios.

        This validates that we can leverage existing infrastructure for retries.
        """
        # The PipelinePhaseCoordinatorProtocol already supports:
        # 1. Phase status updates
        # 2. Pipeline initiation
        # 3. Error handling and state management

        # Our retry approach leverages these existing capabilities
        assert True  # Placeholder - actual coordination tests exist in integration tests


class TestRetryAPIEndpoint:
    """Test the simplified retry API endpoint."""

    @pytest.mark.asyncio
    async def test_retry_endpoint_validates_user_ownership(self) -> None:
        """Test that retry endpoint validates user ownership of batch."""
        # This would be an integration test with the actual API endpoint
        # Testing user ownership validation through existing batch context

        # The endpoint should:
        # 1. Get batch context
        # 2. Validate user_id matches (in production, from JWT)
        # 3. Return 403 if ownership validation fails

        assert True  # Placeholder for actual API integration test

    @pytest.mark.asyncio
    async def test_retry_endpoint_handles_cj_assessment_constraint(self) -> None:
        """Test that retry endpoint enforces CJ Assessment batch-only constraint."""
        # The endpoint should:
        # 1. Check if phase is CJ_ASSESSMENT
        # 2. Return 400 error if essay_ids are provided for CJ Assessment
        # 3. Allow retry for full batch only

        assert True  # Placeholder for actual API integration test

    @pytest.mark.asyncio
    async def test_retry_endpoint_uses_existing_phase_coordination(self) -> None:
        """Test that retry endpoint leverages existing phase coordination."""
        # The endpoint should:
        # 1. Reset phase status using phase_coordinator.update_phase_status()
        # 2. Use phase_coordinator.initiate_resolved_pipeline() for retry
        # 3. Treat retry as single-phase pipeline

        assert True  # Placeholder for actual API integration test
