"""Integration tests for API endpoints."""
from __future__ import annotations

from typing import Dict, Generator, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from prometheus_client import REGISTRY
from quart import Quart
from quart.testing import QuartClient
from quart_dishka import QuartDishka

from common_core.status_enums import BatchStatus, ProcessingStage
from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.models_db import BatchResult, EssayResult
from services.result_aggregator_service.protocols import (
    BatchQueryServiceProtocol,
    CacheManagerProtocol,
    SecurityServiceProtocol,
)


class MockDIProvider(Provider):
    """Mock dependency injection provider for testing."""

    scope = Scope.APP

    def __init__(self) -> None:
        """Initialize test provider with mock services."""
        super().__init__()
        # Create mocks that can be configured in tests
        self._batch_query_service = AsyncMock(spec=BatchQueryServiceProtocol)
        self._security_service = AsyncMock(spec=SecurityServiceProtocol)
        self._cache_manager = AsyncMock(spec=CacheManagerProtocol)

    @provide
    def settings(self) -> Settings:
        """Provide test settings."""
        return Settings(
            SERVICE_NAME="test_aggregator",
            REDIS_URL="redis://localhost:6379",
            DATABASE_URL="postgresql://test:test@localhost/test",
            INTERNAL_API_KEY="test-api-key-123",
            ALLOWED_SERVICE_IDS=["test-service", "api_gateway"],
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            KAFKA_CONSUMER_GROUP_ID="test-group",
            CACHE_ENABLED=False,  # Disable caching for tests
        )

    @provide
    def security_service(self, settings: Settings) -> SecurityServiceProtocol:
        """Provide mock security service."""
        # Configure the mock to return True for valid credentials
        self._security_service.validate_service_credentials.side_effect = (
            lambda api_key, service_id: (
                api_key == settings.INTERNAL_API_KEY and service_id in settings.ALLOWED_SERVICE_IDS
            )
        )
        return self._security_service

    @provide
    def batch_query_service(self) -> BatchQueryServiceProtocol:
        """Provide mock batch query service."""
        return self._batch_query_service

    @provide
    def cache_manager(self) -> CacheManagerProtocol:
        """Provide mock cache manager."""
        return self._cache_manager

    @provide
    def metrics(self) -> ResultAggregatorMetrics:
        """Provide metrics instance."""
        return ResultAggregatorMetrics()


@pytest.fixture(autouse=True)
def clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry before each test."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
    yield


@pytest.fixture
def test_provider() -> MockDIProvider:
    """Create test provider instance."""
    return MockDIProvider()


@pytest.fixture
async def app(test_provider: MockDIProvider) -> Quart:
    """Create test Quart app with dependency injection."""
    app = Quart(__name__)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)

    # Setup DI container
    container = make_async_container(test_provider)
    QuartDishka(app=app, container=container)

    # Store provider for test access
    app.test_provider = test_provider  # type: ignore[attr-defined]

    return app


@pytest.fixture
def client(app: Quart) -> QuartClient:
    """Create test client."""
    return app.test_client()  # type: ignore[return-value]


def create_mock_batch_result(
    batch_id: str,
    user_id: str,
    overall_status: BatchStatus,
    essay_count: int,
    essays: Optional[List[AsyncMock]] = None,
) -> AsyncMock:
    """Create a mock BatchResult for testing."""
    mock_batch = AsyncMock(spec=BatchResult)
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id
    mock_batch.overall_status = overall_status
    mock_batch.essay_count = essay_count
    mock_batch.essays = essays or []
    mock_batch.completed_essay_count = len(
        [e for e in mock_batch.essays if e.spellcheck_status == ProcessingStage.COMPLETED]
    )
    mock_batch.failed_essay_count = len(
        [e for e in mock_batch.essays if e.spellcheck_status == ProcessingStage.FAILED]
    )
    mock_batch.created_at = MagicMock()
    mock_batch.updated_at = MagicMock()
    mock_batch.last_error = None
    mock_batch.requested_pipeline = None  # Set to None or a string value
    mock_batch.processing_started_at = None
    mock_batch.processing_completed_at = None
    return mock_batch


def create_mock_essay_result(
    essay_id: str,
    batch_id: str,
    spellcheck_status: Optional[ProcessingStage] = None,
    spellcheck_correction_count: Optional[int] = None,
    cj_assessment_status: Optional[ProcessingStage] = None,
    cj_rank: Optional[int] = None,
    cj_score: Optional[float] = None,
) -> AsyncMock:
    """Create a mock EssayResult for testing."""
    mock_essay = AsyncMock(spec=EssayResult)
    mock_essay.essay_id = essay_id
    mock_essay.batch_id = batch_id
    mock_essay.spellcheck_status = spellcheck_status  # Keep as enum, not string
    mock_essay.spellcheck_correction_count = spellcheck_correction_count
    mock_essay.cj_assessment_status = cj_assessment_status  # Keep as enum, not string
    mock_essay.cj_rank = cj_rank
    mock_essay.cj_score = cj_score
    mock_essay.filename = None
    mock_essay.spellcheck_corrected_text_storage_id = None
    mock_essay.spellcheck_error = None
    mock_essay.cj_assessment_error = None
    mock_essay.updated_at = MagicMock()
    return mock_essay


class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    async def test_health_check(self, client: QuartClient) -> None:
        """Test the health check endpoint."""
        # Act
        response = await client.get("/healthz")
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert data["status"] == "healthy"
        assert data["service"] == "result_aggregator_service"
        assert data["version"] == "1.0.0"

    async def test_metrics_endpoint(self, client: QuartClient) -> None:
        """Test the metrics endpoint."""
        # Act
        response = await client.get("/metrics")
        data = await response.get_data(as_text=True)

        # Assert
        assert response.status_code == 200
        assert response.content_type == "text/plain; version=0.0.4; charset=utf-8"
        assert "# HELP" in data
        assert "# TYPE" in data


class TestQueryEndpoints:
    """Test cases for query API endpoints."""

    async def test_get_batch_status_success(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test successful batch status retrieval."""
        # Arrange
        batch_id: str = "batch-123"
        mock_essays: List[AsyncMock] = [
            create_mock_essay_result(
                essay_id="essay-1",
                batch_id=batch_id,
                spellcheck_status=ProcessingStage.COMPLETED,
                spellcheck_correction_count=5,
                cj_assessment_status=ProcessingStage.COMPLETED,
                cj_rank=1,
                cj_score=0.95,
            ),
            create_mock_essay_result(
                essay_id="essay-2",
                batch_id=batch_id,
                spellcheck_status=ProcessingStage.COMPLETED,
                spellcheck_correction_count=2,
                cj_assessment_status=ProcessingStage.COMPLETED,
                cj_rank=2,
                cj_score=0.85,
            ),
        ]

        mock_batch: AsyncMock = create_mock_batch_result(
            batch_id=batch_id,
            user_id="user-456",
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            essay_count=2,
            essays=mock_essays,
        )

        # Configure the mock query service
        test_provider._batch_query_service.get_batch_status.return_value = mock_batch

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(f"/internal/v1/batches/{batch_id}/status", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert data["batch_id"] == batch_id
        assert data["user_id"] == "user-456"
        assert data["overall_status"] == "COMPLETED"  # API maps COMPLETED_SUCCESSFULLY to COMPLETED
        assert data["essay_count"] == 2
        assert len(data["essays"]) == 2
        assert data["essays"][0]["essay_id"] == "essay-1"
        assert data["essays"][0]["spellcheck_status"] == "completed"

    async def test_get_batch_status_not_found(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test batch status retrieval when batch doesn't exist."""
        # Arrange
        batch_id: str = "non-existent-batch"

        # Configure the mock to return None
        test_provider._batch_query_service.get_batch_status.return_value = None

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(f"/internal/v1/batches/{batch_id}/status", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 404
        assert data["error"] == "Batch not found"

    async def test_get_batch_status_unauthorized(
        self,
        client: QuartClient,
    ) -> None:
        """Test batch status retrieval with invalid credentials."""
        # Act - No headers
        response = await client.get("/internal/v1/batches/batch-123/status")
        data = await response.get_json()

        # Assert
        assert response.status_code == 401
        assert data["error"] == "Missing authentication"

    async def test_get_batch_status_invalid_api_key(
        self,
        client: QuartClient,
    ) -> None:
        """Test batch status retrieval with wrong API key."""
        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "wrong-key",
            "X-Service-ID": "test-service",
        }
        response = await client.get("/internal/v1/batches/batch-123/status", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 401
        assert data["error"] == "Invalid credentials"

    async def test_get_batch_status_invalid_service_id(
        self,
        client: QuartClient,
    ) -> None:
        """Test batch status retrieval with unauthorized service."""
        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "unauthorized-service",
        }
        response = await client.get("/internal/v1/batches/batch-123/status", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 401
        assert data["error"] == "Invalid credentials"

    async def test_get_user_batches_success(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test successful user batches retrieval."""
        # Arrange
        user_id: str = "user-456"
        mock_batches: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id="batch-1",
                user_id=user_id,
                overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
                essay_count=2,
            ),
            create_mock_batch_result(
                batch_id="batch-2",
                user_id=user_id,
                overall_status=BatchStatus.PROCESSING_PIPELINES,
                essay_count=3,
            ),
        ]

        # Configure the mock to return batches
        test_provider._batch_query_service.get_user_batches.return_value = mock_batches

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(f"/internal/v1/batches/user/{user_id}", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert len(data["batches"]) == 2
        assert data["batches"][0]["batch_id"] == "batch-1"
        assert (
            data["batches"][0]["overall_status"] == "COMPLETED"
        )  # API maps COMPLETED_SUCCESSFULLY to COMPLETED
        assert data["batches"][1]["batch_id"] == "batch-2"
        assert (
            data["batches"][1]["overall_status"] == "PROCESSING"
        )  # API maps PROCESSING_PIPELINES to PROCESSING
        assert data["pagination"]["limit"] == 20
        assert data["pagination"]["offset"] == 0
        assert data["pagination"]["total"] == 2

    async def test_get_user_batches_with_pagination(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test user batches retrieval with pagination parameters."""
        # Arrange
        user_id: str = "user-456"
        mock_batches: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id=f"batch-{i}",
                user_id=user_id,
                overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
                essay_count=1,
            )
            for i in range(5)
        ]

        # Configure the mock to return batches
        test_provider._batch_query_service.get_user_batches.return_value = mock_batches

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(
            f"/internal/v1/batches/user/{user_id}?limit=5&offset=10", headers=headers
        )
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert len(data["batches"]) == 5
        assert data["pagination"]["limit"] == 5
        assert data["pagination"]["offset"] == 10

        # Verify query service was called with correct parameters
        test_provider._batch_query_service.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=None,
            limit=5,
            offset=10,
        )

    async def test_get_user_batches_with_status_filter(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test user batches retrieval with status filter."""
        # Arrange
        user_id: str = "user-456"
        status: str = "completed_successfully"
        mock_batches: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id="batch-1",
                user_id=user_id,
                overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
                essay_count=2,
            ),
        ]

        # Configure the mock to return batches
        test_provider._batch_query_service.get_user_batches.return_value = mock_batches

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(
            f"/internal/v1/batches/user/{user_id}?status={status}", headers=headers
        )
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert len(data["batches"]) == 1
        assert (
            data["batches"][0]["overall_status"] == "COMPLETED"
        )  # API maps completed_successfully to COMPLETED

        # Verify query service was called with status filter
        test_provider._batch_query_service.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=status,
            limit=20,
            offset=0,
        )

    async def test_get_user_batches_empty_result(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test user batches retrieval with no results."""
        # Arrange
        user_id: str = "user-no-batches"

        # Configure the mock to return empty list
        test_provider._batch_query_service.get_user_batches.return_value = []

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(f"/internal/v1/batches/user/{user_id}", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert data["batches"] == []
        assert data["pagination"]["total"] == 0

    async def test_get_user_batches_service_error(
        self,
        client: QuartClient,
        app: Quart,
        test_provider: MockDIProvider,
    ) -> None:
        """Test user batches retrieval when service raises error."""
        # Arrange
        user_id: str = "user-456"

        # Configure the mock to raise an error
        test_provider._batch_query_service.get_user_batches.side_effect = Exception(
            "Database error"
        )

        # Act
        headers: Dict[str, str] = {
            "X-Internal-API-Key": "test-api-key-123",
            "X-Service-ID": "test-service",
        }
        response = await client.get(f"/internal/v1/batches/user/{user_id}", headers=headers)
        data = await response.get_json()

        # Assert
        assert response.status_code == 500
        assert data["error"] == "Internal server error"
