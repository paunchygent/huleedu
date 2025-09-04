"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.events import EventEnvelope
from common_core.status_enums import ProcessingStage
from dishka import AsyncContainer, FromDishka, Provider, Scope, make_async_container, provide
from huleedu_service_libs.protocols import RedisClientProtocol
from prometheus_client import REGISTRY
from quart import Quart
from quart.testing import QuartClient
from quart_dishka import QuartDishka
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
)
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
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


class MockRedisClient:
    """Mock Redis client for testing idempotency."""

    def __init__(self) -> None:
        self.keys: Dict[str, str] = {}
        self.set_calls: List[tuple[str, str, Optional[int]]] = []
        self.delete_calls: List[str] = []

    async def set_if_not_exists(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, str(value), ttl_seconds))
        if key in self.keys:
            return False
        self.keys[key] = str(value)
        return True

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        self.delete_calls.append(key)
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> Optional[str]:
        """Mock GET operation."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        SERVICE_NAME="test-result-aggregator",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_CONSUMER_GROUP_ID="test-group",
        KAFKA_AUTO_OFFSET_RESET="earliest",
        KAFKA_MAX_POLL_RECORDS=100,
        KAFKA_SESSION_TIMEOUT_MS=30000,
    )


@pytest.fixture
def mock_event_processor() -> AsyncMock:
    """Create mock event processor."""
    return AsyncMock(spec=EventProcessorProtocol)


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
def mock_metrics() -> ResultAggregatorMetrics:
    """Create metrics instance."""
    return ResultAggregatorMetrics()


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Create mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def kafka_consumer(
    settings: Settings,
    mock_event_processor: AsyncMock,
    mock_metrics: ResultAggregatorMetrics,
    mock_redis_client: MockRedisClient,
) -> ResultAggregatorKafkaConsumer:
    """Create Kafka consumer instance."""
    return ResultAggregatorKafkaConsumer(
        settings=settings,
        event_processor=mock_event_processor,
        metrics=mock_metrics,
        redis_client=mock_redis_client,  # type: ignore[arg-type]
    )


def create_kafka_record(
    topic: str, event_envelope: EventEnvelope[Any], offset: int = 12345
) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord."""
    # Use Pydantic's model_dump with mode="json" to properly serialize all fields
    envelope_dict = event_envelope.model_dump(mode="json")

    return ConsumerRecord(
        topic=topic,
        partition=0,
        offset=offset,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(envelope_dict).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


# =============================================================================
# Testcontainer Integration Test Fixtures (for API tests with real infrastructure)
# =============================================================================


class IntegrationTestSettings(Settings):
    """Override settings for integration testing."""

    def __init__(self, database_url: str, redis_url: str) -> None:
        # Initialize parent first to set up Pydantic machinery
        super().__init__()
        # Then set our custom attributes
        object.__setattr__(self, "_database_url", database_url)
        self.REDIS_URL = redis_url
        self.CACHE_ENABLED = True
        self.REDIS_CACHE_TTL_SECONDS = 60  # Shorter TTL for testing
        from pydantic import SecretStr

        self.INTERNAL_API_KEY = SecretStr("test-api-key")
        self.ALLOWED_SERVICE_IDS = ["test-service"]

    @property
    def DATABASE_URL(self) -> str:
        """Override to return test database URL."""
        return str(object.__getattribute__(self, "_database_url"))


class IntegrationTestResultAggregatorApp(Quart):
    """Test app with typed attributes."""

    container: AsyncContainer
    consumer_task: Optional[asyncio.Task[None]] = None


class IntegrationTestApiProvider(Provider):
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
        from unittest.mock import AsyncMock

        from services.result_aggregator_service.implementations.aggregator_service_impl import (
            AggregatorServiceImpl,
        )
        from services.result_aggregator_service.implementations.bos_data_transformer import (
            BOSDataTransformer,
        )

        # Use mock BOS client for integration tests
        mock_bos_client = AsyncMock()

        # Configure mock to return None for non-existent batches (simulating BOS 404 response)
        async def mock_get_pipeline_state(batch_id: str) -> Optional[Any]:
            if batch_id == "non-existent-batch":
                return None  # Simulates BOS returning 404, converted to None by client
            # For other test batches, you would return appropriate test data
            return None  # Default to not found for integration tests

        mock_bos_client.get_pipeline_state.side_effect = mock_get_pipeline_state
        bos_transformer = BOSDataTransformer()

        return AggregatorServiceImpl(
            batch_repository, cache_manager, mock_bos_client, bos_transformer, settings
        )

    @provide(scope=Scope.REQUEST)
    def provide_cache_manager(
        self, redis_client: FromDishka[RedisClientProtocol], settings: FromDishka[Settings]
    ) -> CacheManagerProtocol:
        """Provides the real cache manager implementation."""
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
async def integration_test_settings(
    postgres_container: PostgresContainer, redis_container: RedisContainer
) -> IntegrationTestSettings:
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

    return IntegrationTestSettings(database_url=postgres_url, redis_url=redis_url)


@pytest.fixture(scope="function")
async def integration_test_app(
    integration_test_settings: IntegrationTestSettings,
) -> AsyncGenerator[IntegrationTestResultAggregatorApp, None]:
    """Create test Quart application with DI container."""
    from sqlalchemy.ext.asyncio import create_async_engine

    app = IntegrationTestResultAggregatorApp(__name__)

    # Create DI container with test providers
    container = make_async_container(
        CoreInfrastructureProvider(),
        DatabaseProvider(),
        IntegrationTestApiProvider(),  # Use clean test provider instead of ServiceProvider
        context={Settings: integration_test_settings},
    )

    # Setup Dishka integration
    QuartDishka(app=app, container=container)

    # Store container reference (both ways for compatibility)
    app.container = container
    app.dishka_container = container  # type: ignore[attr-defined]  # For the authenticate_request function

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)

    # Initialize database schema using canonical pattern
    engine = create_async_engine(integration_test_settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield app


@pytest.fixture
async def integration_test_client(
    integration_test_app: IntegrationTestResultAggregatorApp,
) -> AsyncGenerator[QuartClient, None]:
    """Create test client."""
    async with integration_test_app.test_app() as app:
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
async def setup_test_data(integration_test_app: IntegrationTestResultAggregatorApp) -> BatchResult:
    """Setup test batch data in database."""
    container = integration_test_app.container

    # Get batch repository from container
    async with container() as request_container:
        repo = await request_container.get(BatchRepositoryProtocol)

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
            correlation_id=uuid4(),
            correction_count=5,
            corrected_text_storage_id="storage-001",
        )

        await repo.update_essay_cj_assessment_result(
            essay_id="essay-001",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            correlation_id=uuid4(),
            rank=1,
            score=0.95,
            comparison_count=10,
        )

        await repo.update_essay_spellcheck_result(
            essay_id="essay-002",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            correlation_id=uuid4(),
            correction_count=3,
            corrected_text_storage_id="storage-002",
        )

        await repo.update_essay_cj_assessment_result(
            essay_id="essay-002",
            batch_id="test-batch-001",
            status=ProcessingStage.COMPLETED,
            correlation_id=uuid4(),
            rank=2,
            score=0.85,
            comparison_count=10,
        )

        # Update batch status
        await repo.update_batch_phase_completed(
            batch_id="test-batch-001", phase="cj_assessment", completed_count=2, failed_count=0
        )

        # Return fresh batch
        batch_result = await repo.get_batch("test-batch-001")
        assert batch_result is not None
        return batch_result  # type: ignore[no-any-return]
