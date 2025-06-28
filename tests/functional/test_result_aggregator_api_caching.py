"""Functional tests for API endpoints with cache validation."""

import asyncio
from typing import Any, AsyncGenerator, Optional, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from dishka import AsyncContainer, FromDishka, Provider, Scope, make_async_container, provide
from huleedu_service_libs.protocols import RedisClientProtocol
from quart import Quart
from quart.testing import QuartClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from common_core.status_enums import ProcessingStage
from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
    RepositoryProvider,
)
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.models_db import Base, BatchResult
from services.result_aggregator_service.protocols import (
    BatchQueryServiceProtocol,
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    SecurityServiceProtocol,
    StateStoreProtocol,
)


class FunctionalTestSettings(Settings):
    """Override settings for testing."""

    def __init__(self, database_url: str, redis_url: str) -> None:
        super().__init__()
        self.DATABASE_URL = database_url
        self.REDIS_URL = redis_url
        self.CACHE_ENABLED = True
        self.REDIS_CACHE_TTL_SECONDS = 60  # Shorter TTL for testing
        self.INTERNAL_API_KEY = "test-api-key"
        self.ALLOWED_SERVICE_IDS = ["test-service"]


class FunctionalTestResultAggregatorApp(Quart):
    """Test app with typed attributes."""

    container: AsyncContainer
    consumer_task: Optional[asyncio.Task[None]] = None


class FunctionalTestApiProvider(Provider):
    """Clean test provider that replaces ServiceProvider entirely."""

    @provide(scope=Scope.APP)
    def provide_security_service(self) -> SecurityServiceProtocol:
        """Provides a mock security service that validates based on credentials."""
        mock_security = AsyncMock(spec=SecurityServiceProtocol)

        # Configure to check actual credentials
        async def validate_credentials(api_key: str, service_id: str) -> bool:
            return api_key == "test-api-key" and service_id == "test-service"

        mock_security.validate_service_credentials.side_effect = validate_credentials
        return mock_security

    @provide(scope=Scope.REQUEST)
    def provide_batch_query_service(
        self,
        batch_repository: FromDishka[BatchRepositoryProtocol],
        cache_manager: FromDishka[CacheManagerProtocol],
        settings: FromDishka[Settings],
    ) -> BatchQueryServiceProtocol:
        """Provides the REAL implementation of the query service."""
        from services.result_aggregator_service.implementations.aggregator_service_impl import (
            AggregatorServiceImpl,
        )

        return AggregatorServiceImpl(batch_repository, cache_manager, settings)

    @provide(scope=Scope.REQUEST)
    def provide_cache_manager(
        self, redis_client: FromDishka[RedisClientProtocol], settings: FromDishka[Settings]
    ) -> CacheManagerProtocol:
        """Provides the real cache manager implementation."""
        from typing import cast

        from huleedu_service_libs.redis_client import RedisClient
        from huleedu_service_libs.redis_set_operations import RedisSetOperations

        from services.result_aggregator_service.implementations.cache_manager_impl import (
            CacheManagerImpl,
        )

        # Follow the same pattern as the service DI
        client = cast(RedisClient, redis_client)
        redis_set_ops = RedisSetOperations(client.client, f"test-{settings.SERVICE_NAME}")
        return CacheManagerImpl(redis_client, redis_set_ops, settings.REDIS_CACHE_TTL_SECONDS)

    @provide(scope=Scope.APP)
    def provide_event_processor(self) -> EventProcessorProtocol:
        """Provide a mock event processor for testing."""
        mock_processor = AsyncMock(spec=EventProcessorProtocol)
        return mock_processor

    @provide(scope=Scope.REQUEST)
    def provide_state_store(
        self, redis_client: FromDishka[RedisClientProtocol]
    ) -> StateStoreProtocol:
        """Provides the real state store implementation."""
        from services.result_aggregator_service.implementations.state_store_redis_impl import (
            StateStoreRedisImpl,
        )

        return StateStoreRedisImpl(redis_client)

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> ResultAggregatorMetrics:
        """Provide metrics instance for tests."""
        # Create a new instance for each test to avoid registry conflicts
        import prometheus_client

        # Clear the default registry to avoid conflicts between tests
        prometheus_client.REGISTRY._collector_to_names.clear()
        prometheus_client.REGISTRY._names_to_collectors.clear()
        return ResultAggregatorMetrics()


@pytest.fixture(scope="function")
async def postgres_container() -> AsyncGenerator[PostgresContainer, None]:
    """Create PostgreSQL container."""
    with PostgresContainer("postgres:15") as container:
        yield container


@pytest.fixture(scope="function")
async def redis_container() -> AsyncGenerator[RedisContainer, None]:
    """Create Redis container."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="function")
async def test_settings(
    postgres_container: PostgresContainer, redis_container: RedisContainer
) -> FunctionalTestSettings:
    """Create test settings with container URLs."""
    # Get PostgreSQL connection URL and ensure it uses asyncpg
    postgres_url = postgres_container.get_connection_url()
    if "+psycopg2://" in postgres_url:
        postgres_url = postgres_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in postgres_url:
        postgres_url = postgres_url.replace("postgresql://", "postgresql+asyncpg://")

    # Build Redis URL from container info
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    return FunctionalTestSettings(database_url=postgres_url, redis_url=redis_url)


@pytest.fixture(scope="function")
async def test_app(
    test_settings: FunctionalTestSettings,
) -> AsyncGenerator[FunctionalTestResultAggregatorApp, None]:
    """Create test Quart application with DI container."""
    app = FunctionalTestResultAggregatorApp(__name__)

    # Create DI container with test providers
    container = make_async_container(
        CoreInfrastructureProvider(),
        DatabaseProvider(),
        RepositoryProvider(),
        FunctionalTestApiProvider(),  # Use clean test provider instead of ServiceProvider
        context={Settings: test_settings},
    )

    # Setup Dishka integration
    QuartDishka(app=app, container=container)

    # Store container reference (both ways for compatibility)
    app.container = container
    app.dishka_container = container  # type: ignore[attr-defined]  # For the authenticate_request function

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)

    # Initialize database schema
    async with app.container() as request_container:
        engine = await request_container.get(AsyncEngine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    yield app


@pytest.fixture
async def client(test_app: FunctionalTestResultAggregatorApp) -> AsyncGenerator[QuartClient, None]:
    """Create test client."""
    async with test_app.test_app() as app:
        async with app.test_client() as client:
            yield cast(QuartClient, client)


@pytest.fixture
async def auth_headers() -> dict[str, str]:
    """Create authentication headers for internal API calls."""
    return {
        "X-Internal-API-Key": "test-api-key",
        "X-Service-ID": "test-service",
        "X-Correlation-ID": str(uuid4()),
    }


@pytest.fixture
async def setup_test_data(test_app: FunctionalTestResultAggregatorApp) -> BatchResult:
    """Setup test batch data in database."""
    container = test_app.container

    # Get database session
    async with container() as request_container:
        session = await request_container.get(AsyncSession)
        repo = BatchRepositoryPostgresImpl(session)

        # Create test batch
        await repo.create_batch(
            batch_id="test-batch-001",
            user_id="test-user-123",
            essay_count=2,
            metadata={"test": True},
        )

        # Add essay results
        await repo.update_essay_spellcheck_result(
            essay_id="essay-001",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            correction_count=5,
            corrected_text_storage_id="storage-001",
        )

        await repo.update_essay_cj_assessment_result(
            essay_id="essay-001",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            rank=1,
            score=0.95,
            comparison_count=10,
        )

        await repo.update_essay_spellcheck_result(
            essay_id="essay-002",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            correction_count=3,
            corrected_text_storage_id="storage-002",
        )

        await repo.update_essay_cj_assessment_result(
            essay_id="essay-002",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            rank=2,
            score=0.85,
            comparison_count=10,
        )

        # Update batch status
        await repo.update_batch_phase_completed(
            batch_id="test-batch-001", phase="cj_assessment", completed_count=2, failed_count=0
        )

        await session.commit()

        # Return fresh batch
        batch_result = await repo.get_batch("test-batch-001")
        assert batch_result is not None
        return batch_result


@pytest.mark.functional
@pytest.mark.asyncio
class TestAPIWithCaching:
    """Functional tests for API endpoints with cache validation."""

    async def test_get_batch_status_cache_flow(
        self,
        client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        test_app: FunctionalTestResultAggregatorApp,
    ) -> None:
        """Test complete cache flow for get_batch_status endpoint."""
        batch_id = "test-batch-001"
        endpoint = f"/internal/v1/batches/{batch_id}/status"

        # Track database queries
        query_count = 0
        original_get_batch = BatchRepositoryPostgresImpl.get_batch

        async def mock_get_batch(self: Any, batch_id: str) -> Optional[BatchResult]:
            nonlocal query_count
            query_count += 1
            return await original_get_batch(self, batch_id)

        with patch.object(BatchRepositoryPostgresImpl, "get_batch", mock_get_batch):
            # Step 1: Cache Miss - First request should hit database
            response1 = await client.get(endpoint, headers=auth_headers)
            if response1.status_code != 200:
                error_body = await response1.get_json()
                print(f"Error response: {response1.status_code} - {error_body}")
            assert response1.status_code == 200
            data1 = await response1.get_json()

            # Verify response structure
            assert data1["batch_id"] == batch_id
            assert data1["user_id"] == "test-user-123"
            assert data1["overall_status"] == "COMPLETED"  # API enum value
            assert len(data1["essays"]) == 2

            # Verify database was queried
            assert query_count == 1

            # Step 2: Cache Hit - Second request should use cache
            response2 = await client.get(endpoint, headers=auth_headers)
            assert response2.status_code == 200
            data2 = await response2.get_json()

            # Response should be identical
            assert data2 == data1

            # Database should NOT be queried again
            assert query_count == 1  # Still 1, no new query

            # Step 3: Cache Invalidation - Simulate batch update
            async with test_app.container() as container:
                cache_manager = await container.get(CacheManagerProtocol)
                await cache_manager.invalidate_batch(batch_id)

            # Step 4: Verify Invalidation - Third request should hit database again
            response3 = await client.get(endpoint, headers=auth_headers)
            assert response3.status_code == 200
            data3 = await response3.get_json()

            # Response should still be the same
            assert data3 == data1

            # Database should be queried again after invalidation
            assert query_count == 2

    async def test_get_user_batches_cache_flow(
        self,
        client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        test_app: FunctionalTestResultAggregatorApp,
    ) -> None:
        """Test cache flow for get_user_batches endpoint."""
        user_id = "test-user-123"
        endpoint = f"/internal/v1/batches/user/{user_id}"

        # Create additional batches for pagination testing
        async with test_app.container() as container:
            session = await container.get(AsyncSession)
            repo = BatchRepositoryPostgresImpl(session)

            # Create more batches
            for i in range(2, 5):
                await repo.create_batch(
                    batch_id=f"test-batch-{i:03d}", user_id=user_id, essay_count=1
                )
            await session.commit()

        # Track database queries
        query_count = 0
        original_get_user_batches = BatchRepositoryPostgresImpl.get_user_batches

        async def mock_get_user_batches(
            self: Any, user_id: str, **kwargs: Any
        ) -> list[BatchResult]:
            nonlocal query_count
            query_count += 1
            return await original_get_user_batches(self, user_id, **kwargs)

        with patch.object(BatchRepositoryPostgresImpl, "get_user_batches", mock_get_user_batches):
            # Test with query parameters
            params = {"limit": 2, "offset": 0, "status": "completed_successfully"}

            # Step 1: Cache Miss
            response1 = await client.get(endpoint, headers=auth_headers, query_string=params)
            assert response1.status_code == 200
            data1 = await response1.get_json()

            assert "batches" in data1
            assert len(data1["batches"]) == 1  # Only one completed batch
            assert data1["batches"][0]["batch_id"] == "test-batch-001"
            assert query_count == 1

            # Step 2: Cache Hit
            response2 = await client.get(endpoint, headers=auth_headers, query_string=params)
            assert response2.status_code == 200
            data2 = await response2.get_json()

            assert data2 == data1
            assert query_count == 1  # No new query

            # Step 3: Different parameters should cache separately
            params2 = {"limit": 10, "offset": 0}  # No status filter
            response3 = await client.get(endpoint, headers=auth_headers, query_string=params2)
            assert response3.status_code == 200
            data3 = await response3.get_json()

            assert len(data3["batches"]) == 4  # All batches
            assert query_count == 2  # New query for different params

    async def test_cache_disabled_behavior(
        self,
        client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        test_app: FunctionalTestResultAggregatorApp,
    ) -> None:
        """Test API behavior when caching is disabled."""
        # Temporarily disable caching
        async with test_app.container() as container:
            settings = await container.get(Settings)
            original_cache_enabled = settings.CACHE_ENABLED
            settings.CACHE_ENABLED = False

        try:
            batch_id = "test-batch-001"
            endpoint = f"/internal/v1/batches/{batch_id}/status"

            # Track database queries
            query_count = 0
            original_get_batch = BatchRepositoryPostgresImpl.get_batch

            async def mock_get_batch(self: Any, batch_id: str) -> Optional[BatchResult]:
                nonlocal query_count
                query_count += 1
                return await original_get_batch(self, batch_id)

            with patch.object(BatchRepositoryPostgresImpl, "get_batch", mock_get_batch):
                # Make multiple requests
                for i in range(3):
                    response = await client.get(endpoint, headers=auth_headers)
                    assert response.status_code == 200

                # Each request should hit the database when caching is disabled
                assert query_count == 3

        finally:
            # Restore cache setting
            async with test_app.container() as container:
                settings = await container.get(Settings)
                settings.CACHE_ENABLED = original_cache_enabled

    async def test_authentication_failure(
        self, client: QuartClient, setup_test_data: BatchResult
    ) -> None:
        """Test API authentication requirements."""
        endpoint = "/internal/v1/batches/test-batch-001/status"

        # No headers
        response = await client.get(endpoint)
        assert response.status_code == 401

        # Missing API key
        response = await client.get(endpoint, headers={"X-Service-ID": "test-service"})
        assert response.status_code == 401

        # Invalid API key
        response = await client.get(
            endpoint, headers={"X-Internal-API-Key": "wrong-key", "X-Service-ID": "test-service"}
        )
        assert response.status_code == 401

    async def test_batch_not_found(self, client: QuartClient, auth_headers: dict[str, str]) -> None:
        """Test 404 response for non-existent batch."""
        endpoint = "/internal/v1/batches/non-existent-batch/status"

        response = await client.get(endpoint, headers=auth_headers)
        assert response.status_code == 404

        data = await response.get_json()
        assert data["error"] == "Batch not found"

    async def test_concurrent_cache_operations(
        self, client: QuartClient, auth_headers: dict[str, str], setup_test_data: BatchResult
    ) -> None:
        """Test cache behavior under concurrent requests."""
        import asyncio

        batch_id = "test-batch-001"
        endpoint = f"/internal/v1/batches/{batch_id}/status"

        # Make 10 concurrent requests
        async def make_request() -> int:
            response = await client.get(endpoint, headers=auth_headers)
            return response.status_code

        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All requests should succeed
        assert all(status == 200 for status in results)

        # Verify cache metrics if available
        # In a real implementation, we'd check Prometheus metrics here
