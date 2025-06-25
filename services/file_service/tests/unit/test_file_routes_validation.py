"""Integration tests for file routes with batch state validation."""

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


class TestFileRoutesValidation:
    @pytest.fixture
    def mock_batch_validator(self) -> AsyncMock:
        """Create mock batch state validator."""
        return AsyncMock(spec=BatchStateValidatorProtocol)

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
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock(spec=EventPublisherProtocol)

    @pytest.fixture
    async def app_client(
        self,
        mock_batch_validator: AsyncMock,
        mock_text_extractor: AsyncMock,
        mock_content_validator: AsyncMock,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.

        This fixture correctly overrides the production providers with test providers
        that supply our mocks. This is the standard way to test DI-based applications.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_batch_validator(self) -> BatchStateValidatorProtocol:
                return mock_batch_validator

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
            def provide_event_publisher(self) -> EventPublisherProtocol:
                return mock_event_publisher

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

    async def test_upload_batch_files_blocked_when_locked(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test file upload blocked when batch is locked for processing."""
        # Configure validator to return locked status
        mock_batch_validator.can_modify_batch_files.return_value = (
            False,
            "Batch is locked: Spellcheck has started",
        )

        # Create test file data
        file_data = BytesIO(b"Test essay content")
        file_data.name = "test_essay.txt"

        # Make request with proper multipart form data format
        response = await app_client.post(
            "/v1/files/batch",
            form={"batch_id": "test-batch-123", "files": (file_data, "test_essay.txt")},
            headers={"X-User-ID": "test-user-456"},
        )

        # Should return 409 Conflict
        assert response.status_code == 409

        data = await response.get_json()
        assert "error" in data
        assert "Cannot add files to batch" in data["error"]

        # Verify validator was called
        mock_batch_validator.can_modify_batch_files.assert_called_once_with(
            "test-batch-123", "test-user-456"
        )

    async def test_upload_batch_files_missing_user_id(self, app_client: QuartTestClient) -> None:
        """Test file upload fails without user authentication."""
        file_data = BytesIO(b"Test essay content")
        file_data.name = "test_essay.txt"

        # Make request without X-User-ID header
        response = await app_client.post(
            "/v1/files/batch",
            form={"batch_id": "test-batch-123", "files": (file_data, "test_essay.txt")},
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

        data = await response.get_json()
        assert "error" in data
        assert "authentication" in data["error"].lower()

    async def test_upload_batch_files_missing_batch_id(self, app_client: QuartTestClient) -> None:
        """Test file upload fails without batch_id in form data."""
        file_data = BytesIO(b"Test essay content")
        file_data.name = "test_essay.txt"

        # Make request without batch_id in form
        response = await app_client.post(
            "/v1/files/batch",
            form={"files": (file_data, "test_essay.txt")},
            headers={"X-User-ID": "test-user-456"},
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

        data = await response.get_json()
        assert "error" in data
        assert "batch_id is required" in data["error"]

    async def test_upload_batch_files_no_files_provided(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test file upload fails when no files are provided."""
        # Configure validator to allow modifications
        mock_batch_validator.can_modify_batch_files.return_value = (True, "Batch can be modified")

        # Make request with batch_id but no files in 'files' field
        response = await app_client.post(
            "/v1/files/batch",
            form={
                "batch_id": "test-batch-123",
                "files": [],  # Empty files list
            },
            headers={"X-User-ID": "test-user-456"},
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

        data = await response.get_json()
        assert "error" in data
        assert "No files provided in 'files' field" in data["error"]

    async def test_upload_batch_files_success_returns_202(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test successful file upload returns 202 Accepted with proper JSON structure."""
        # Configure validator to allow modifications
        mock_batch_validator.can_modify_batch_files.return_value = (True, "Batch can be modified")

        # Create proper FileStorage object for Quart test client
        file_data = BytesIO(b"Test essay content")
        file_storage = FileStorage(
            stream=file_data, filename="test_essay.txt", content_type="text/plain"
        )

        # Make valid request using Quart test client format
        # Note: Quart test client expects files as a dict mapping field names to FileStorage objects
        response = await app_client.post(
            "/v1/files/batch",
            form={"batch_id": "test-batch-123"},
            files={
                "files": file_storage  # Single file for the 'files' field
            },
            headers={"X-User-ID": "test-user-456"},
        )

        # Debug: Print response details if not 202
        if response.status_code != 202:
            error_data = await response.get_json()
            print(f"Response status: {response.status_code}")
            print(f"Response data: {error_data}")

            # Also check if the request was processed at all
            mock_batch_validator.can_modify_batch_files.assert_called_once_with(
                "test-batch-123", "test-user-456"
            )

        # Should return 202 Accepted (fire-and-forget async pattern)
        assert response.status_code == 202

        data = await response.get_json()

        # Verify JSON structure for async processing
        assert "message" in data
        assert "batch_id" in data
        assert "correlation_id" in data

        assert data["batch_id"] == "test-batch-123"
        assert "1 files received" in data["message"]
        assert "are being processed" in data["message"]

        # Verify correlation_id is a valid UUID string
        import uuid

        uuid.UUID(data["correlation_id"])  # Should not raise exception

    async def test_upload_multiple_files_returns_202(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test multiple files upload in single request returns 202 with correct file count."""
        # Configure validator to allow modifications
        mock_batch_validator.can_modify_batch_files.return_value = (True, "Batch can be modified")

        # For testing YOUR architecture (multiple files with same field name),
        # we need to manually construct multipart form data since Quart's test client
        # has limitations with multiple files using the same field name

        boundary = "----QuartTestBoundary"

        # Construct multipart form data manually
        form_data = "------QuartTestBoundary\r\n"
        form_data += 'Content-Disposition: form-data; name="batch_id"\r\n\r\n'
        form_data += "test-batch-456\r\n"

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

        # Test YOUR actual architecture - single request with multiple files using same field name
        response = await app_client.post(
            "/v1/files/batch",
            data=form_data_bytes,
            headers={
                "X-User-ID": "test-user-789",
                "Content-Type": "multipart/form-data; boundary=----QuartTestBoundary",
                "Content-Length": str(len(form_data_bytes)),
            },
        )

        # Should return 202 Accepted (fire-and-forget async pattern)
        assert response.status_code == 202

        data = await response.get_json()

        # Verify YOUR architecture's response format
        assert data["batch_id"] == "test-batch-456"
        assert "2 files received" in data["message"]  # YOUR endpoint reports total count
        assert "correlation_id" in data

        # Verify single correlation ID shared by all files (YOUR design)
        import uuid

        uuid.UUID(data["correlation_id"])  # Should not raise exception

        # Verify batch validator was called once before processing any files
        mock_batch_validator.can_modify_batch_files.assert_called_once_with(
            "test-batch-456", "test-user-789"
        )

    async def test_correlation_id_header_handling(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test that provided correlation ID is used in response."""
        # Configure validator to allow modifications
        mock_batch_validator.can_modify_batch_files.return_value = (True, "Batch can be modified")

        # Create FileStorage object
        file_data = BytesIO(b"Test essay content")
        file_storage = FileStorage(
            stream=file_data, filename="test_essay.txt", content_type="text/plain"
        )

        # Provide correlation ID in header
        test_correlation_id = "12345678-1234-5678-9abc-123456789abc"

        # Make request with correlation ID header
        response = await app_client.post(
            "/v1/files/batch",
            form={"batch_id": "test-batch-789"},
            files={"files": file_storage},
            headers={"X-User-ID": "test-user-999", "X-Correlation-ID": test_correlation_id},
        )

        # Should return 202 Accepted
        assert response.status_code == 202

        data = await response.get_json()

        # Should use provided correlation ID
        assert data["correlation_id"] == test_correlation_id

    async def test_invalid_correlation_id_generates_new_one(
        self, app_client: QuartTestClient, mock_batch_validator: AsyncMock
    ) -> None:
        """Test that invalid correlation ID generates a new one."""
        # Configure validator to allow modifications
        mock_batch_validator.can_modify_batch_files.return_value = (True, "Batch can be modified")

        # Create FileStorage object
        file_data = BytesIO(b"Test essay content")
        file_storage = FileStorage(
            stream=file_data, filename="test_essay.txt", content_type="text/plain"
        )

        # Make request with invalid correlation ID
        response = await app_client.post(
            "/v1/files/batch",
            form={"batch_id": "test-batch-999"},
            files={"files": file_storage},
            headers={"X-User-ID": "test-user-111", "X-Correlation-ID": "invalid-uuid-format"},
        )

        # Should return 202 Accepted
        assert response.status_code == 202

        data = await response.get_json()

        # Should generate new valid UUID (not the invalid one)
        assert data["correlation_id"] != "invalid-uuid-format"

        # Verify it's a valid UUID
        import uuid

        uuid.UUID(data["correlation_id"])  # Should not raise exception
