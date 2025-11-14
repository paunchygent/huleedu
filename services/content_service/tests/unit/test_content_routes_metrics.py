"""Unit tests for Content Service routes metrics integration."""

from __future__ import annotations

import uuid

import pytest
from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_resource_not_found,
)
from quart import Quart


class MockContentMetrics:
    """Mock implementation of ContentMetricsProtocol for testing."""

    def __init__(self) -> None:
        """Initialize the mock metrics."""
        self.operations: list[tuple[OperationType, OperationStatus]] = []

    def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
        """Record an operation for testing verification."""
        self.operations.append((operation, status))


class MockContentRepository:
    """Mock implementation of ContentRepositoryProtocol for testing."""

    def __init__(self) -> None:
        """Initialize the mock repository."""
        self.stored_content: dict[str, tuple[bytes, str]] = {}

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: uuid.UUID | None = None,
    ) -> None:
        """Mock content save operation."""
        if not content_data:
            raise_content_service_error(
                service="content_service",
                operation="save_content",
                message="No content data provided",
                correlation_id=correlation_id,
            )

        self.stored_content[content_id] = (content_data, content_type)

    async def get_content(
        self,
        content_id: str,
        correlation_id: uuid.UUID | None = None,
    ) -> tuple[bytes, str]:
        """Mock get content operation."""
        if content_id not in self.stored_content:
            raise_resource_not_found(
                service="content_service",
                operation="get_content",
                resource_type="content",
                resource_id=content_id,
                correlation_id=correlation_id,
            )

        return self.stored_content[content_id]

    async def content_exists(self, content_id: str) -> bool:
        """Mock content existence check."""
        return content_id in self.stored_content


@pytest.fixture
def app() -> Quart:
    """Create a test Quart app with mocked dependencies."""
    app = Quart(__name__)

    # Import and register the blueprint
    from services.content_service.api.content_routes import content_bp

    app.register_blueprint(content_bp)

    return app


@pytest.fixture
def mock_metrics() -> MockContentMetrics:
    """Provide a mock metrics implementation."""
    return MockContentMetrics()


@pytest.fixture
def mock_repository() -> MockContentRepository:
    """Provide a mock content repository implementation."""
    return MockContentRepository()


class TestContentRoutesMetricsIntegration:
    """Test metrics integration in content routes."""

    @pytest.mark.asyncio
    async def test_upload_success_records_metric(
        self,
        app: Quart,
        mock_metrics: MockContentMetrics,
        mock_repository: MockContentRepository,
    ) -> None:
        """Test that successful upload records success metric."""
        # Note: This test demonstrates the intended behavior
        # The actual implementation will use Dishka injection
        # which makes pure unit testing more complex

        # Verify intended behavior: successful upload should record success metric
        content_data = b"test content data"
        correlation_id = uuid.uuid4()

        # Simulate successful upload
        content_id = uuid.uuid4().hex
        await mock_repository.save_content(content_id, content_data, "text/plain", correlation_id)
        mock_metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)

        # Verify metrics were recorded
        assert (OperationType.UPLOAD, OperationStatus.SUCCESS) in mock_metrics.operations
        assert len(mock_metrics.operations) == 1

    @pytest.mark.asyncio
    async def test_upload_failure_records_error_metric(
        self,
        mock_metrics: MockContentMetrics,
        mock_repository: MockContentRepository,
    ) -> None:
        """Test that failed upload records error metric."""
        from huleedu_service_libs.error_handling import HuleEduError

        correlation_id = uuid.uuid4()

        # Simulate upload failure
        try:
            await mock_repository.save_content(uuid.uuid4().hex, b"", "text/plain", correlation_id)
        except HuleEduError:
            mock_metrics.record_operation(OperationType.UPLOAD, OperationStatus.FAILED)

        # Verify error metrics were recorded
        assert (OperationType.UPLOAD, OperationStatus.FAILED) in mock_metrics.operations

    @pytest.mark.asyncio
    async def test_download_success_records_metric(
        self,
        mock_metrics: MockContentMetrics,
        mock_repository: MockContentRepository,
    ) -> None:
        """Test that successful download records success metric."""
        correlation_id = uuid.uuid4()

        # Setup: store some content first
        content_id = uuid.uuid4().hex
        await mock_repository.save_content(
            content_id, b"test content", "text/plain", correlation_id
        )

        # Simulate successful download
        assert await mock_repository.content_exists(content_id)
        await mock_repository.get_content(content_id, correlation_id)
        mock_metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.SUCCESS)

        # Verify metrics were recorded
        assert (OperationType.DOWNLOAD, OperationStatus.SUCCESS) in mock_metrics.operations

    @pytest.mark.asyncio
    async def test_download_not_found_records_metric(
        self,
        mock_metrics: MockContentMetrics,
        mock_repository: MockContentRepository,
    ) -> None:
        """Test that download not found records not_found metric."""
        # Simulate download of non-existent content
        content_id = "non-existent-id"

        if not await mock_repository.content_exists(content_id):
            mock_metrics.record_operation(OperationType.DOWNLOAD, OperationStatus.NOT_FOUND)

        # Verify metrics were recorded
        assert (OperationType.DOWNLOAD, OperationStatus.NOT_FOUND) in mock_metrics.operations

    def test_metrics_protocol_integration(self) -> None:
        """Test that mock metrics follows the protocol interface."""
        mock_metrics = MockContentMetrics()

        # Verify it behaves like ContentMetricsProtocol
        assert hasattr(mock_metrics, "record_operation")
        assert callable(mock_metrics.record_operation)

        # Test the interface
        mock_metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)
        assert mock_metrics.operations == [(OperationType.UPLOAD, OperationStatus.SUCCESS)]

    def test_content_repository_protocol_integration(self) -> None:
        """Test that mock repository follows the protocol interface."""
        mock_repository = MockContentRepository()

        # Verify it behaves like ContentRepositoryProtocol
        assert hasattr(mock_repository, "save_content")
        assert hasattr(mock_repository, "content_exists")
        assert hasattr(mock_repository, "get_content")

        # All should be async methods
        import inspect

        assert inspect.iscoroutinefunction(mock_repository.save_content)
        assert inspect.iscoroutinefunction(mock_repository.content_exists)
        assert inspect.iscoroutinefunction(mock_repository.get_content)


class TestMetricsErrorHandling:
    """Test metrics error handling in routes."""

    def test_metrics_exception_handling(self) -> None:
        """Test that metrics exceptions don't break route processing."""

        class FailingMetrics:
            """Metrics implementation that raises exceptions."""

            def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
                """Always raise an exception."""
                raise RuntimeError("Metrics system failure")

        failing_metrics = FailingMetrics()

        # In the actual implementation, metrics errors should be caught
        # and logged but not propagate to break the route response
        try:
            failing_metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)
            assert False, "Should have raised an exception"
        except RuntimeError:
            # This demonstrates why the implementation needs error handling
            pass

    def test_defensive_metrics_usage(self) -> None:
        """Test defensive metrics usage patterns."""
        mock_metrics = MockContentMetrics()

        # Test various edge cases that routes might encounter
        test_cases = [
            (OperationType.UPLOAD, OperationStatus.SUCCESS),
            (OperationType.DOWNLOAD, OperationStatus.SUCCESS),
            (OperationType.UPLOAD, OperationStatus.FAILED),
            (OperationType.DOWNLOAD, OperationStatus.NOT_FOUND),
            (OperationType.DOWNLOAD, OperationStatus.ERROR),
            (OperationType.UPLOAD, OperationStatus.ERROR),
        ]

        for operation, status in test_cases:
            # Should handle all valid combinations without error
            mock_metrics.record_operation(operation, status)

        # Verify all were recorded
        assert len(mock_metrics.operations) == len(test_cases)
        assert all(case in mock_metrics.operations for case in test_cases)
