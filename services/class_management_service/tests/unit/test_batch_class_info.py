"""
Unit tests for batch class info endpoint and related components.

Tests the GET /internal/v1/batches/class-info endpoint for batch→class lookup
via EssayStudentAssociation.

Following HuleEdu testing patterns: mock at protocol boundaries, explicit imports.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from services.class_management_service.implementations.class_management_service_impl import (
    ClassManagementServiceImpl,
)
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassRepositoryProtocol,
)


class TestRepositoryGetClassInfoForBatches:
    """Test suite for repository get_class_info_for_batches method."""

    def test_repository_has_get_class_info_for_batches_method(self) -> None:
        """Test repository implements the get_class_info_for_batches method."""
        # Arrange
        mock_engine = AsyncMock(spec=AsyncEngine)

        # Act
        repo = PostgreSQLClassRepositoryImpl[UserClass, Student](mock_engine, None)

        # Assert
        assert hasattr(repo, "get_class_info_for_batches")
        assert callable(repo.get_class_info_for_batches)


class TestServiceGetClassInfoForBatches:
    """Test suite for service get_class_info_for_batches method."""

    @pytest.mark.asyncio
    async def test_service_delegates_to_repository(self) -> None:
        """Test service method delegates to repository correctly."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_id_1 = uuid.uuid4()
        batch_id_2 = uuid.uuid4()
        batch_ids = [batch_id_1, batch_id_2]

        expected_result = {
            str(batch_id_1): {"class_id": str(uuid.uuid4()), "class_name": "Class A"},
            str(batch_id_2): None,
        }
        mock_repo.get_class_info_for_batches.return_value = expected_result

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches(batch_ids)

        # Assert
        assert result == expected_result
        mock_repo.get_class_info_for_batches.assert_called_once_with(batch_ids)

    @pytest.mark.asyncio
    async def test_service_handles_empty_batch_ids(self) -> None:
        """Test service handles empty batch_ids list correctly."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        mock_repo.get_class_info_for_batches.return_value = {}

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches([])

        # Assert
        assert result == {}
        mock_repo.get_class_info_for_batches.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_service_returns_all_null_for_batches_without_associations(self) -> None:
        """Test service returns null for batches without class associations."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_id = uuid.uuid4()
        expected_result = {str(batch_id): None}
        mock_repo.get_class_info_for_batches.return_value = expected_result

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches([batch_id])

        # Assert
        assert result[str(batch_id)] is None


class TestBatchClassInfoResponseFormat:
    """Test suite for batch class info response format validation."""

    @pytest.mark.asyncio
    async def test_response_format_with_class_info(self) -> None:
        """Test response format when class info exists."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_id = uuid.uuid4()
        class_id = uuid.uuid4()
        class_name = "English 5 - Group A"

        mock_repo.get_class_info_for_batches.return_value = {
            str(batch_id): {"class_id": str(class_id), "class_name": class_name}
        }

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches([batch_id])

        # Assert - verify structure
        assert str(batch_id) in result
        class_info = result[str(batch_id)]
        assert class_info is not None
        assert "class_id" in class_info
        assert "class_name" in class_info
        assert class_info["class_id"] == str(class_id)
        assert class_info["class_name"] == class_name

    @pytest.mark.asyncio
    async def test_response_format_mixed_batches(self) -> None:
        """Test response format with mix of found and not-found batches."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_with_class = uuid.uuid4()
        batch_without_class = uuid.uuid4()
        class_id = uuid.uuid4()

        mock_repo.get_class_info_for_batches.return_value = {
            str(batch_with_class): {"class_id": str(class_id), "class_name": "Test Class"},
            str(batch_without_class): None,
        }

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches([batch_with_class, batch_without_class])

        # Assert
        assert len(result) == 2
        assert result[str(batch_with_class)] is not None
        assert result[str(batch_without_class)] is None


class TestBatchClassInfoEdgeCases:
    """Test suite for edge cases in batch class info retrieval."""

    @pytest.mark.asyncio
    async def test_single_batch_id(self) -> None:
        """Test retrieval with single batch ID."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_id = uuid.uuid4()
        class_id = uuid.uuid4()

        mock_repo.get_class_info_for_batches.return_value = {
            str(batch_id): {"class_id": str(class_id), "class_name": "Single Class"}
        }

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches([batch_id])

        # Assert
        assert len(result) == 1
        assert str(batch_id) in result

    @pytest.mark.asyncio
    async def test_multiple_batch_ids(self) -> None:
        """Test retrieval with multiple batch IDs."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        batch_ids = [uuid.uuid4() for _ in range(5)]

        # Simulate alternating found/not-found pattern
        expected_result: dict[str, dict[str, str] | None] = {}
        for i, bid in enumerate(batch_ids):
            if i % 2 == 0:
                expected_result[str(bid)] = {
                    "class_id": str(uuid.uuid4()),
                    "class_name": f"Class {i}",
                }
            else:
                expected_result[str(bid)] = None

        mock_repo.get_class_info_for_batches.return_value = expected_result

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act
        result = await service.get_class_info_for_batches(batch_ids)

        # Assert
        assert len(result) == 5
        # Verify alternating pattern
        for i, bid in enumerate(batch_ids):
            if i % 2 == 0:
                assert result[str(bid)] is not None
            else:
                assert result[str(bid)] is None

    @pytest.mark.asyncio
    async def test_repository_error_propagates(self) -> None:
        """Test that repository errors propagate correctly."""
        # Arrange
        mock_repo = AsyncMock(spec=ClassRepositoryProtocol)
        mock_publisher = AsyncMock(spec=ClassEventPublisherProtocol)

        mock_repo.get_class_info_for_batches.side_effect = RuntimeError("Database connection lost")

        service = ClassManagementServiceImpl(
            repo=mock_repo,
            event_publisher=mock_publisher,
            user_class_type=UserClass,
            student_type=Student,
        )

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database connection lost"):
            await service.get_class_info_for_batches([uuid.uuid4()])
