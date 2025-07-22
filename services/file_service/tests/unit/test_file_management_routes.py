"""
Integration tests for file management API routes.

Tests the new file management endpoints: GET /batch/<batch_id>/state,
POST /batch/<batch_id>/files, and DELETE /batch/<batch_id>/files/<essay_id>
following the established Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart.datastructures import FileStorage
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.file_service.app import app
from services.file_service.protocols import (
    BatchStateValidatorProtocol,
    ContentServiceClientProtocol,
    ContentValidatorProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)


class TestFileManagementRoutes:
    """Test file management API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_batch_validator(self) -> AsyncMock:
        """Create mock batch state validator."""
        return AsyncMock(spec=BatchStateValidatorProtocol)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock(spec=EventPublisherProtocol)

    @pytest.fixture
    def mock_text_extractor(self) -> AsyncMock:
        """Create mock text extractor."""
        return AsyncMock(spec=TextExtractorProtocol)

    @pytest.fixture
    def mock_content_validator(self) -> AsyncMock:
        """Create mock content validator."""
        return AsyncMock(spec=ContentValidatorProtocol)

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content service client."""
        return AsyncMock(spec=ContentServiceClientProtocol)

    @pytest.fixture
    async def app_client(
        self,
        mock_batch_validator: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_batch_validator(self) -> BatchStateValidatorProtocol:
                return mock_batch_validator

            @provide(scope=Scope.APP)
            def provide_event_publisher(self) -> EventPublisherProtocol:
                return mock_event_publisher

            @provide(scope=Scope.APP)
            def provide_text_extractor(self) -> TextExtractorProtocol:
                return mock_text_extractor

            @provide(scope=Scope.APP)
            def provide_content_validator(self) -> ContentValidatorProtocol:
                return mock_content_validator

            @provide(scope=Scope.APP)
            def provide_content_client(self) -> ContentServiceClientProtocol:
                return mock_content_client

            @provide(scope=Scope.APP)
            def provide_metrics(self) -> dict[str, Any]:
                """Provide mock metrics dictionary."""
                return {}

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    async def test_get_batch_state_success(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
    ) -> None:
        """Test successful batch state retrieval."""
        # Arrange
        batch_id = "test-batch-123"
        user_id = "user-456"
        lock_status = {
            "is_locked": False,
            "pipeline_state": "READY",
            "reason": "Batch is ready for modifications",
        }
        mock_batch_validator.get_batch_lock_status.return_value = lock_status

        # Act
        response = await app_client.get(
            f"/v1/files/batch/{batch_id}/state", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["batch_id"] == batch_id
        assert data["lock_status"] == lock_status
        # Assert - correlation_id is auto-generated, so we just check it was called once
        mock_batch_validator.get_batch_lock_status.assert_called_once()
        # Verify the first argument is batch_id and second is UUID
        call_args = mock_batch_validator.get_batch_lock_status.call_args[0]
        assert call_args[0] == batch_id
        assert len(call_args) == 2  # batch_id + correlation_id

    async def test_get_batch_state_no_auth(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test batch state retrieval without authentication."""
        # Arrange
        batch_id = "test-batch-123"

        # Act
        response = await app_client.get(f"/v1/files/batch/{batch_id}/state")

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "User authentication required"

    async def test_get_batch_state_validator_error(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
    ) -> None:
        """Test batch state retrieval when validator raises error."""
        # Arrange
        batch_id = "test-batch-123"
        user_id = "user-456"
        mock_batch_validator.get_batch_lock_status.side_effect = Exception("Validator error")

        # Act
        response = await app_client.get(
            f"/v1/files/batch/{batch_id}/state", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 500
        data = await response.get_json()
        assert data["error"] == "Internal server error"

    async def test_add_files_to_batch_success(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test successful file addition to batch."""
        # Arrange
        batch_id = "test-batch-123"
        user_id = "user-456"
        # Mock no exception (successful validation)
        mock_batch_validator.can_modify_batch_files.return_value = None

        # Create proper FileStorage object for Quart test client
        file_data = BytesIO(b"Test essay content")
        file_storage = FileStorage(
            stream=file_data, filename="test_essay.txt", content_type="text/plain"
        )

        # Act - using the correct Quart test client pattern
        response = await app_client.post(
            f"/v1/files/batch/{batch_id}/files",
            files={
                "files": file_storage  # Single file for the 'files' field
            },
            headers={"X-User-ID": user_id},
        )

        # Assert
        assert response.status_code == 202
        data = await response.get_json()
        assert batch_id in data["message"]
        assert data["batch_id"] == batch_id
        assert "correlation_id" in data
        assert data["added_files"] == 1

        # Assert - correlation_id is auto-generated, so we just check it was called once
        mock_batch_validator.can_modify_batch_files.assert_called_once()
        # Verify the arguments are batch_id, user_id, and correlation_id UUID
        call_args = mock_batch_validator.can_modify_batch_files.call_args[0]
        assert call_args[0] == batch_id
        assert call_args[1] == user_id
        assert len(call_args) == 3  # batch_id + user_id + correlation_id

        # Verify event publishing was called
        mock_event_publisher.publish_batch_file_added_v1.assert_called_once()

    async def test_add_files_to_batch_no_auth(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test file addition without authentication."""
        # Arrange
        batch_id = "test-batch-123"

        # Act
        response = await app_client.post(f"/v1/files/batch/{batch_id}/files")

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "User authentication required"

    async def test_add_files_to_batch_locked(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
    ) -> None:
        """Test file addition when batch is locked."""
        # Arrange
        batch_id = "test-batch-123"
        user_id = "user-456"
        # Mock HuleEduError for batch lock scenario
        from huleedu_service_libs.error_handling import raise_processing_error
        def mock_locked_batch(*args):
            raise_processing_error(
                service="file_service",
                operation="can_modify_batch_files",
                message="Batch is currently being processed",
                correlation_id=args[2],  # correlation_id is third argument
                batch_id=args[0],
            )
        mock_batch_validator.can_modify_batch_files.side_effect = mock_locked_batch

        # Act
        response = await app_client.post(
            f"/v1/files/batch/{batch_id}/files", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 409
        data = await response.get_json()
        assert data["error"] == "Cannot add files to batch"
        assert "Batch is currently being processed" in data["reason"]
        assert data["batch_id"] == batch_id

    async def test_add_files_to_batch_no_files(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
    ) -> None:
        """Test file addition with no files provided."""
        # Arrange
        batch_id = "test-batch-123"
        user_id = "user-456"
        # Mock no exception (successful validation)
        mock_batch_validator.can_modify_batch_files.return_value = None

        # Act
        response = await app_client.post(
            f"/v1/files/batch/{batch_id}/files", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 400
        data = await response.get_json()
        assert data["error"] == "No files provided in 'files' field."

    async def test_add_multiple_files_to_batch(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test multiple files addition using manual multipart form construction."""
        # Arrange
        batch_id = "test-batch-456"
        user_id = "user-789"
        # Mock no exception (successful validation)
        mock_batch_validator.can_modify_batch_files.return_value = None

        # Manual multipart form construction for multiple files with same field name
        # boundary = "----QuartTestBoundary" # Removed as unused
        form_data = "------QuartTestBoundary\r\n"

        # First file
        form_data += "------QuartTestBoundary\r\n"
        form_data += 'Content-Disposition: form-data; name="files"; filename="essay1.txt"\r\n'
        form_data += "Content-Type: text/plain\r\n\r\n"
        form_data += "First essay content\r\n"

        # Second file
        form_data += "------QuartTestBoundary\r\n"
        form_data += 'Content-Disposition: form-data; name="files"; filename="essay2.txt"\r\n'
        form_data += "Content-Type: text/plain\r\n\r\n"
        form_data += "Second essay content\r\n"

        form_data += "------QuartTestBoundary--\r\n"

        # Convert to bytes
        form_data_bytes = form_data.encode("utf-8")

        # Act
        response = await app_client.post(
            f"/v1/files/batch/{batch_id}/files",
            data=form_data_bytes,
            headers={
                "X-User-ID": user_id,
                "Content-Type": "multipart/form-data; boundary=----QuartTestBoundary",
                "Content-Length": str(len(form_data_bytes)),
            },
        )

        # Assert
        assert response.status_code == 202
        data = await response.get_json()
        assert data["batch_id"] == batch_id
        assert "2 files added" in data["message"]
        assert data["added_files"] == 2

        # Assert - correlation_id is auto-generated, so we just check it was called once
        mock_batch_validator.can_modify_batch_files.assert_called_once()
        # Verify the arguments are batch_id, user_id, and correlation_id UUID
        call_args = mock_batch_validator.can_modify_batch_files.call_args[0]
        assert call_args[0] == batch_id
        assert call_args[1] == user_id
        assert len(call_args) == 3  # batch_id + user_id + correlation_id

        # Verify event publishing was called twice (once per file)
        assert mock_event_publisher.publish_batch_file_added_v1.call_count == 2

    async def test_remove_file_from_batch_success(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test successful file removal from batch."""
        # Arrange
        batch_id = "test-batch-123"
        essay_id = "essay-456"
        user_id = "user-789"
        # Mock no exception (successful validation)
        mock_batch_validator.can_modify_batch_files.return_value = None

        # Act
        response = await app_client.delete(
            f"/v1/files/batch/{batch_id}/files/{essay_id}", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert essay_id in data["message"]
        assert data["batch_id"] == batch_id
        assert data["essay_id"] == essay_id
        assert "correlation_id" in data

        # Assert - correlation_id is auto-generated, so we just check it was called once
        mock_batch_validator.can_modify_batch_files.assert_called_once()
        # Verify the arguments are batch_id, user_id, and correlation_id UUID
        call_args = mock_batch_validator.can_modify_batch_files.call_args[0]
        assert call_args[0] == batch_id
        assert call_args[1] == user_id
        assert len(call_args) == 3  # batch_id + user_id + correlation_id

        # Verify event publishing was called
        mock_event_publisher.publish_batch_file_removed_v1.assert_called_once()

    async def test_remove_file_from_batch_no_auth(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test file removal without authentication."""
        # Arrange
        batch_id = "test-batch-123"
        essay_id = "essay-456"

        # Act
        response = await app_client.delete(f"/v1/files/batch/{batch_id}/files/{essay_id}")

        # Assert
        assert response.status_code == 401
        data = await response.get_json()
        assert data["error"] == "User authentication required"

    async def test_remove_file_from_batch_locked(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
    ) -> None:
        """Test file removal when batch is locked."""
        # Arrange
        batch_id = "test-batch-123"
        essay_id = "essay-456"
        user_id = "user-789"
        # Mock HuleEduError for batch lock scenario
        from huleedu_service_libs.error_handling import raise_processing_error
        def mock_locked_batch(*args):
            raise_processing_error(
                service="file_service",
                operation="can_modify_batch_files",
                message="Batch is currently being processed",
                correlation_id=args[2],  # correlation_id is third argument
                batch_id=args[0],
            )
        mock_batch_validator.can_modify_batch_files.side_effect = mock_locked_batch

        # Act
        response = await app_client.delete(
            f"/v1/files/batch/{batch_id}/files/{essay_id}", headers={"X-User-ID": user_id}
        )

        # Assert
        assert response.status_code == 409
        data = await response.get_json()
        assert data["error"] == "Cannot remove file from batch"
        assert "Batch is currently being processed" in data["reason"]
        assert data["batch_id"] == batch_id
        assert data["essay_id"] == essay_id

    async def test_correlation_id_handling(
        self,
        app_client: QuartTestClient,
        mock_batch_validator: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test proper correlation ID handling in endpoints."""
        # Arrange
        batch_id = "test-batch-123"
        essay_id = "essay-456"
        user_id = "user-789"
        correlation_id = "12345678-1234-5678-9abc-123456789abc"
        # Mock no exception (successful validation)
        mock_batch_validator.can_modify_batch_files.return_value = None

        # Act
        response = await app_client.delete(
            f"/v1/files/batch/{batch_id}/files/{essay_id}",
            headers={"X-User-ID": user_id, "X-Correlation-ID": correlation_id},
        )

        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["correlation_id"] == correlation_id
