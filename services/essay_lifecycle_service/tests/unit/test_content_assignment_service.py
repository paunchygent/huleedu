"""
Unit tests for ContentAssignmentService domain service.

Tests the atomic content-to-essay assignment logic that is shared between
normal content provisioning flow and pending content recovery flow.

Following test methodology 075: Protocol-based DI testing with comprehensive
parametrized coverage of domain-specific scenarios.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.domain_services.content_assignment_service import (
    ContentAssignmentService,
)
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
)


class TestContentAssignmentService:
    """Tests for ContentAssignmentService domain service."""

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Create mock BatchEssayTracker with protocol compliance."""
        return AsyncMock(spec=BatchEssayTracker)

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock EssayRepositoryProtocol with protocol compliance."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_publisher(self) -> AsyncMock:
        """Create mock BatchLifecyclePublisher with protocol compliance."""
        return AsyncMock(spec=BatchLifecyclePublisher)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(
        self,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
    ) -> ContentAssignmentService:
        """Create ContentAssignmentService with mocked dependencies."""
        return ContentAssignmentService(
            batch_tracker=mock_batch_tracker,
            repository=mock_repository,
            batch_lifecycle_publisher=mock_publisher,
        )

    @pytest.fixture
    def sample_content_metadata(self) -> dict[str, Any]:
        """Create sample content metadata for testing."""
        return {
            "original_file_name": "test_essay.docx",
            "file_size_bytes": 2048,
            "file_upload_id": str(uuid4()),
            "content_md5_hash": "abc123def456",
        }

    @pytest.mark.parametrize(
        "slot_assignment_result, repository_result, expected_outcome",
        [
            # Successful new assignment
            ("essay_123", (True, "essay_123"), (True, "essay_123")),
            # Idempotent assignment (content already assigned)
            ("essay_456", (False, "essay_456"), (False, "essay_456")),
            # No available slots
            (None, None, (False, None)),
        ],
    )
    async def test_assign_content_to_essay_basic_scenarios(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
        slot_assignment_result: str | None,
        repository_result: tuple[bool, str] | None,
        expected_outcome: tuple[bool, str | None],
    ) -> None:
        """Test basic assignment scenarios: success, idempotency, no slots."""
        # Arrange
        batch_id = "test_batch_001"
        text_storage_id = "text_storage_123"
        correlation_id = uuid4()

        mock_batch_tracker.assign_slot_to_content.return_value = slot_assignment_result
        if repository_result:
            mock_repository.create_essay_state_with_content_idempotency.return_value = (
                repository_result
            )
            # Mock mark_slot_fulfilled to return None (no batch completion) for basic scenarios
            mock_batch_tracker.mark_slot_fulfilled.return_value = None

        # Act
        result = await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        assert result == expected_outcome

        # Verify slot assignment was attempted
        mock_batch_tracker.assign_slot_to_content.assert_called_once_with(
            batch_id, text_storage_id, sample_content_metadata["original_file_name"]
        )

        if slot_assignment_result is None:
            # No slots available - should not proceed to database operations
            mock_repository.create_essay_state_with_content_idempotency.assert_not_called()
            mock_publisher.publish_essay_slot_assigned.assert_not_called()
        else:
            # Slot assigned - should proceed with database operations
            mock_repository.create_essay_state_with_content_idempotency.assert_called_once()

            # Verify essay data structure
            call_args = mock_repository.create_essay_state_with_content_idempotency.call_args
            essay_data = call_args.kwargs["essay_data"]
            assert essay_data["internal_essay_id"] == slot_assignment_result
            assert essay_data["initial_status"] == EssayStatus.READY_FOR_PROCESSING
            assert essay_data["original_file_name"] == sample_content_metadata["original_file_name"]

    async def test_assign_content_to_essay_slot_persistence_on_creation(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
    ) -> None:
        """Test that slot assignment is persisted only when content is newly created."""
        # Arrange
        batch_id = "test_batch_002"
        text_storage_id = "text_storage_456"
        correlation_id = uuid4()
        assigned_essay_id = "essay_789"

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,  # was_created = True
            assigned_essay_id,
        )
        mock_batch_tracker.mark_slot_fulfilled.return_value = None  # No batch completion

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Should persist slot assignment since was_created=True
        mock_batch_tracker.persist_slot_assignment.assert_called_once_with(
            batch_id,
            assigned_essay_id,
            text_storage_id,
            sample_content_metadata["original_file_name"],
            session=mock_session,
        )

        # Should publish slot assigned event
        mock_publisher.publish_essay_slot_assigned.assert_called_once()

        # Should mark slot as fulfilled
        mock_batch_tracker.mark_slot_fulfilled.assert_called_once_with(
            batch_id, assigned_essay_id, text_storage_id
        )

    async def test_assign_content_to_essay_no_persistence_on_idempotent(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
    ) -> None:
        """Test that slot assignment is not persisted for idempotent cases."""
        # Arrange
        batch_id = "test_batch_003"
        text_storage_id = "text_storage_789"
        correlation_id = uuid4()
        assigned_essay_id = "essay_999"

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            False,  # was_created = False (idempotent)
            assigned_essay_id,
        )
        mock_batch_tracker.mark_slot_fulfilled.return_value = None  # No batch completion

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Should NOT persist slot assignment since was_created=False (idempotent case)
        mock_batch_tracker.persist_slot_assignment.assert_not_called()

        # Should still publish slot assigned event for traceability
        mock_publisher.publish_essay_slot_assigned.assert_called_once()

        # Should still mark slot as fulfilled
        mock_batch_tracker.mark_slot_fulfilled.assert_called_once_with(
            batch_id, assigned_essay_id, text_storage_id
        )

    @pytest.mark.parametrize(
        "class_type, should_cleanup",
        [
            ("GUEST", True),  # GUEST batches are cleaned up
            ("REGULAR", False),  # REGULAR batches are not cleaned up
        ],
    )
    async def test_assign_content_to_essay_batch_completion_cleanup(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
        class_type: str,
        should_cleanup: bool,
    ) -> None:
        """Test batch completion behavior and cleanup for GUEST vs REGULAR batches."""
        # Arrange
        batch_id = f"test_batch_{class_type.lower()}"
        text_storage_id = "text_storage_completion"
        correlation_id = uuid4()
        assigned_essay_id = "essay_completion"

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,
            assigned_essay_id,
        )

        # Mock batch completion with proper essay data structure
        batch_ready_event = AsyncMock()
        batch_ready_event.batch_id = batch_id
        batch_ready_event.ready_essays = [
            {
                "essay_id": assigned_essay_id,
                "text_storage_id": text_storage_id,
                "batch_id": batch_id,
            }
        ]
        batch_ready_event.course_code = "ENG5"
        batch_ready_event.class_type = class_type

        original_correlation_id = uuid4()
        mock_batch_tracker.mark_slot_fulfilled.return_value = (
            batch_ready_event,
            original_correlation_id,
        )
        mock_batch_tracker.get_batch_status.return_value = {"user_id": "test_user"}

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Should publish batch content provisioning completed event
        mock_publisher.publish_batch_content_provisioning_completed.assert_called_once()

        # Verify event data structure
        call_args = mock_publisher.publish_batch_content_provisioning_completed.call_args
        event_data = call_args.kwargs["event_data"]
        assert event_data.batch_id == batch_id
        assert event_data.provisioned_count == 1
        assert event_data.expected_count == 1
        assert event_data.user_id == "test_user"

        # Verify cleanup behavior
        if should_cleanup:
            mock_batch_tracker.cleanup_batch.assert_called_once_with(batch_id)
        else:
            mock_batch_tracker.cleanup_batch.assert_not_called()

    async def test_assign_content_to_essay_event_structure_validation(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
    ) -> None:
        """Test that published events have correct structure and data."""
        # Arrange
        batch_id = "test_batch_events"
        text_storage_id = "text_storage_events"
        correlation_id = uuid4()
        assigned_essay_id = "essay_events"

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,
            assigned_essay_id,
        )
        mock_batch_tracker.mark_slot_fulfilled.return_value = None  # No batch completion

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Verify EssaySlotAssignedV1 event structure
        mock_publisher.publish_essay_slot_assigned.assert_called_once()
        slot_event_call = mock_publisher.publish_essay_slot_assigned.call_args
        slot_event = slot_event_call.kwargs["event_data"]

        assert slot_event.batch_id == batch_id
        assert slot_event.essay_id == assigned_essay_id
        assert slot_event.text_storage_id == text_storage_id
        assert slot_event.file_upload_id == sample_content_metadata["file_upload_id"]
        assert slot_event_call.kwargs["correlation_id"] == correlation_id
        assert slot_event_call.kwargs["session"] == mock_session

    async def test_assign_content_to_essay_correlation_id_propagation(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
        sample_content_metadata: dict[str, Any],
    ) -> None:
        """Test that correlation IDs are properly propagated through all operations."""
        # Arrange
        batch_id = "test_batch_correlation"
        text_storage_id = "text_storage_correlation"
        correlation_id = uuid4()
        assigned_essay_id = "essay_correlation"

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,
            assigned_essay_id,
        )
        mock_batch_tracker.mark_slot_fulfilled.return_value = None

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=sample_content_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Verify correlation ID is passed to repository
        repo_call = mock_repository.create_essay_state_with_content_idempotency.call_args
        assert repo_call.kwargs["correlation_id"] == correlation_id

        # Verify correlation ID is passed to event publishing
        event_call = mock_publisher.publish_essay_slot_assigned.call_args
        assert event_call.kwargs["correlation_id"] == correlation_id

    async def test_assign_content_to_essay_metadata_handling(
        self,
        service: ContentAssignmentService,
        mock_batch_tracker: AsyncMock,
        mock_repository: AsyncMock,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling of various content metadata scenarios including missing fields."""
        # Arrange
        batch_id = "test_batch_metadata"
        text_storage_id = "text_storage_metadata"
        correlation_id = uuid4()
        assigned_essay_id = "essay_metadata"

        # Test metadata with missing optional fields
        incomplete_metadata = {
            "original_file_name": "test.docx",
            # Missing file_size_bytes, file_upload_id, content_md5_hash
        }

        mock_batch_tracker.assign_slot_to_content.return_value = assigned_essay_id
        mock_repository.create_essay_state_with_content_idempotency.return_value = (
            True,
            assigned_essay_id,
        )
        mock_batch_tracker.mark_slot_fulfilled.return_value = None

        # Act
        await service.assign_content_to_essay(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            content_metadata=incomplete_metadata,
            correlation_id=correlation_id,
            session=mock_session,
        )

        # Assert
        # Verify essay data handles missing fields gracefully
        repo_call = mock_repository.create_essay_state_with_content_idempotency.call_args
        essay_data = repo_call.kwargs["essay_data"]

        assert essay_data["original_file_name"] == "test.docx"
        assert essay_data["file_size"] == 0  # Default for missing file_size_bytes
        assert essay_data["file_upload_id"] is None  # Default for missing file_upload_id
        assert essay_data["content_hash"] is None  # Default for missing content_md5_hash
