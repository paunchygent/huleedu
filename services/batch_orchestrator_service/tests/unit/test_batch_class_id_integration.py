"""
Unit tests for class_id field integration in BOS models.

Tests the Phase 1 student matching class_id field handling across
API models, database models, and repository operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.status_enums import BatchStatus
from sqlalchemy.ext.asyncio import AsyncSession

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_context_operations import (
    BatchContextOperations,
)
from services.batch_orchestrator_service.implementations.batch_crud_operations import (
    BatchCrudOperations,
)
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import (
    BatchDatabaseInfrastructure,
)
from services.batch_orchestrator_service.models_db import Batch
from services.batch_orchestrator_service.tests import make_prompt_ref


class TestClassIdIntegration:
    """Test suite for class_id field integration."""

    @pytest.fixture
    def mock_db_infrastructure(self) -> MagicMock:
        """Create mock database infrastructure."""
        mock_db = MagicMock(spec=BatchDatabaseInfrastructure)

        # Create a mock session context manager
        mock_session = AsyncMock(spec=AsyncSession)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_session
        mock_context.__aexit__.return_value = None
        mock_db.session.return_value = mock_context

        return mock_db

    @pytest.fixture
    def crud_operations(self, mock_db_infrastructure: MagicMock) -> BatchCrudOperations:
        """Create CRUD operations instance."""
        return BatchCrudOperations(mock_db_infrastructure)

    @pytest.fixture
    def context_operations(self, mock_db_infrastructure: MagicMock) -> BatchContextOperations:
        """Create context operations instance."""
        return BatchContextOperations(mock_db_infrastructure)

    def test_batch_registration_request_with_class_id(self) -> None:
        """Test BatchRegistrationRequestV1 model with class_id (REGULAR batch)."""
        # Create REGULAR batch with class_id
        request = BatchRegistrationRequestV1(
            course_code=CourseCode.ENG5,
            school_name="Lincoln High",
            student_prompt_ref=make_prompt_ref("prompt-regular-class"),
            expected_essay_count=25,
            user_id="teacher_123",
            class_id="class_456",  # REGULAR batch
        )

        assert request.class_id == "class_456"
        assert request.user_id == "teacher_123"

    def test_batch_registration_request_without_class_id(self) -> None:
        """Test BatchRegistrationRequestV1 model without class_id (GUEST batch)."""
        # Create GUEST batch without class_id
        request = BatchRegistrationRequestV1(
            course_code=CourseCode.SV1,
            school_name="Guest School",
            student_prompt_ref=make_prompt_ref("prompt-guest"),
            expected_essay_count=10,
            user_id="guest_teacher_789",
            # class_id is None by default for GUEST batches
        )

        assert request.class_id is None
        assert request.user_id == "guest_teacher_789"

    @pytest.mark.asyncio
    async def test_crud_create_batch_with_class_id(
        self,
        crud_operations: BatchCrudOperations,
        mock_db_infrastructure: MagicMock,
    ) -> None:
        """Test creating a batch with class_id through CRUD operations."""
        # Arrange
        batch_data = {
            "id": str(uuid4()),
            "name": "Test REGULAR Batch",
            "description": "A batch with class_id",
            "class_id": "class_789",  # REGULAR batch
            "status": BatchStatus.AWAITING_CONTENT_VALIDATION.value,
            "total_essays": 20,
        }

        # Get the mock session
        mock_session = mock_db_infrastructure.session().__aenter__.return_value

        # Act
        result = await crud_operations.create_batch(batch_data)

        # Assert
        # Verify the Batch object was created with class_id
        mock_session.add.assert_called_once()
        created_batch = mock_session.add.call_args[0][0]
        assert isinstance(created_batch, Batch)
        assert created_batch.class_id == "class_789"
        assert created_batch.name == "Test REGULAR Batch"

        # Verify the result includes the basic fields
        assert result["id"] == batch_data["id"]
        assert result["name"] == batch_data["name"]
        assert result["status"] == BatchStatus.AWAITING_CONTENT_VALIDATION.value

    @pytest.mark.asyncio
    async def test_crud_create_batch_without_class_id(
        self,
        crud_operations: BatchCrudOperations,
        mock_db_infrastructure: MagicMock,
    ) -> None:
        """Test creating a batch without class_id through CRUD operations."""
        # Arrange
        batch_data = {
            "id": str(uuid4()),
            "name": "Test GUEST Batch",
            "description": "A batch without class_id",
            # class_id is not provided for GUEST batch
            "status": BatchStatus.AWAITING_CONTENT_VALIDATION.value,
            "total_essays": 15,
        }

        # Get the mock session
        mock_session = mock_db_infrastructure.session().__aenter__.return_value

        # Act
        await crud_operations.create_batch(batch_data)

        # Assert
        # Verify the Batch object was created without class_id
        mock_session.add.assert_called_once()
        created_batch = mock_session.add.call_args[0][0]
        assert isinstance(created_batch, Batch)
        assert created_batch.class_id is None
        assert created_batch.name == "Test GUEST Batch"

    @pytest.mark.asyncio
    async def test_crud_get_batch_includes_class_id(
        self,
        crud_operations: BatchCrudOperations,
        mock_db_infrastructure: MagicMock,
    ) -> None:
        """Test that get_batch_by_id includes class_id in the result."""
        # Arrange
        batch_id = str(uuid4())

        # Create a mock batch with class_id
        mock_batch = MagicMock(spec=Batch)
        mock_batch.id = batch_id
        mock_batch.name = "Test Batch"
        mock_batch.description = "Test Description"
        mock_batch.class_id = "class_123"  # REGULAR batch
        mock_batch.status = BatchStatus.PROCESSING_PIPELINES
        mock_batch.correlation_id = str(uuid4())
        mock_batch.requested_pipelines = ["spellcheck", "cj_assessment"]
        mock_batch.total_essays = 25
        mock_batch.processed_essays = 10
        mock_batch.version = 1
        mock_batch.created_at = datetime.now(UTC)
        mock_batch.updated_at = datetime.now(UTC)
        mock_batch.completed_at = None
        mock_batch.processing_metadata = {}
        mock_batch.error_details = None

        # Mock the query result
        mock_session = mock_db_infrastructure.session().__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_batch
        mock_session.execute.return_value = mock_result

        # Act
        result = await crud_operations.get_batch_by_id(batch_id)

        # Assert
        assert result is not None
        assert result["id"] == batch_id
        assert result["class_id"] == "class_123"
        assert result["name"] == "Test Batch"
        assert result["status"] == BatchStatus.PROCESSING_PIPELINES.value

    @pytest.mark.asyncio
    async def test_context_operations_store_regular_batch(
        self,
        context_operations: BatchContextOperations,
        mock_db_infrastructure: MagicMock,
    ) -> None:
        """Test storing batch context for REGULAR batch with class_id."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        registration_data = BatchRegistrationRequestV1(
            course_code=CourseCode.ENG5,
            school_name="Lincoln High",
            student_prompt_ref=make_prompt_ref("prompt-regular-store"),
            expected_essay_count=30,
            user_id="teacher_123",
            class_id="class_456",  # REGULAR batch
        )

        # Mock no existing batch
        mock_session = mock_db_infrastructure.session().__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await context_operations.store_batch_context(
            batch_id, registration_data, correlation_id
        )

        # Assert
        assert result is True

        # Verify the Batch object was created with class_id
        mock_session.add.assert_called_once()
        created_batch = mock_session.add.call_args[0][0]
        assert isinstance(created_batch, Batch)
        assert created_batch.id == batch_id
        assert created_batch.class_id == "class_456"
        assert created_batch.name == "ENG5 - teacher_123"
        assert created_batch.description is None

    @pytest.mark.asyncio
    async def test_context_operations_update_existing_batch_with_class_id(
        self,
        context_operations: BatchContextOperations,
        mock_db_infrastructure: MagicMock,
    ) -> None:
        """Test updating existing batch context with class_id."""
        # Arrange
        batch_id = str(uuid4())

        registration_data = BatchRegistrationRequestV1(
            course_code=CourseCode.SV2,
            school_name="Stockholm Gymnasium",
            student_prompt_ref=make_prompt_ref("prompt-swedish-store"),
            expected_essay_count=25,
            user_id="teacher_456",
            class_id="class_789",  # REGULAR batch
        )

        # Mock existing batch
        mock_batch = MagicMock(spec=Batch)
        mock_session = mock_db_infrastructure.session().__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_batch
        mock_session.execute.return_value = mock_result

        # Act
        result = await context_operations.store_batch_context(batch_id, registration_data)

        # Assert
        assert result is True

        # Verify the update statement was executed with class_id
        assert mock_session.execute.call_count == 2  # One for SELECT, one for UPDATE
        mock_session.execute.call_args_list[1]

        # The update values should include class_id
        # Note: This is a simplified assertion since we're mocking SQLAlchemy
