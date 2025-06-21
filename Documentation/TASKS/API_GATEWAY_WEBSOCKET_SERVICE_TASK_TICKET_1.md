# Implementation Guide: HuleEdu Client Interface Layer (1/3)

This document provides a step-by-step implementation plan for the foundational components of the client interface layer.

## Part 1: Foundational Layer (BOS API, Query Pattern & Result Aggregator)

This part covers the critical prerequisite of creating a new internal API endpoint in the Batch Orchestrator Service (BOS), fixing event parsing compliance, and building the `result_aggregator_service` to use these new components. This sequence is mandatory to ensure that the services built in Part 2 and 3 have the necessary infrastructure to function correctly.

### Checkpoint 1.1: Extend Shared Redis Client for Pub/Sub (Complete Implementation)

**Objective**: Enhance our existing `RedisClient` in `huleedu-service-libs` to support the WebSocket backplane. This extension is foundational for the real-time communication required by the frontend, enabling a responsive user experience.

**Context and Rationale**:
Our real-time architecture depends on a "backplane"—a messaging system that allows multiple, independent instances of our API Gateway to communicate with backend services without knowing about each other. Redis Pub/Sub is the industry-standard solution for this. It provides a lightweight, high-speed channel where backend services can "publish" UI update events. The API Gateway instances will "subscribe" to these channels and forward the messages to the specific WebSocket clients they are connected to. This decouples the stateful WebSocket connections from our stateless backend, which is essential for horizontal scaling.

**Affected Files**:

- `services/libs/huleedu_service_libs/redis_client.py`
- `services/libs/huleedu_service_libs/protocols.py`

**Implementation Steps**:

1. **Update `AtomicRedisClientProtocol`**: Add `publish` and `subscribe` methods to the protocol definition. This ensures any service depending on this protocol can be type-checked correctly, maintaining our commitment to type safety.

    **File**: `services/libs/huleedu_service_libs/protocols.py`

    ```python
    // ... existing protocol code ...
    
    from contextlib import asynccontextmanager
    from typing import AsyncGenerator
    import redis.client

    class AtomicRedisClientProtocol(RedisClientProtocol, Protocol):
        // ... existing methods: watch, multi, exec, etc. ...

        async def publish(self, channel: str, message: str) -> int:
            """
            Publish a message to a Redis channel. This is a "fire-and-forget"
            operation that sends the message to all active subscribers of the channel.

            Args:
                channel: The channel to publish to (e.g., "ws:user_123").
                message: The message payload to publish, typically a JSON string.

            Returns:
                The integer number of clients that received the message.
            """
            ...

        @asynccontextmanager
        async def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
            """
            Subscribe to a Redis channel within an async context manager, ensuring
            proper connection and disconnection.

            Args:
                channel: The channel to subscribe to.

            Yields:
                A PubSub object that can be iterated over to listen for messages.
            """
            ...
    ```

2. **Implement `publish` and `subscribe` in `RedisClient`**: Add the concrete implementations to the main client class. It is critical to use `aclose()` instead of the deprecated `close()` to ensure the underlying connection pool is managed correctly by the `redis-py` async library, preventing resource leaks.

    **File**: `services/libs/huleedu_service_libs/redis_client.py`

    ```python
    import json
    from contextlib import asynccontextmanager
    from typing import AsyncGenerator
    import redis.client

    // ... existing RedisClient class code ...

    class RedisClient:
        // ... existing methods ...

        async def publish(self, channel: str, message: str) -> int:
            """
            Publish a message to a Redis channel with proper error handling and logging.
            
            CRITICAL: This method enables the WebSocket backplane by allowing backend
            services to publish real-time updates to user-specific channels.
            """
            if not self._started:
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
            
            try:
                # Publish message and get subscriber count
                receiver_count = await self.client.publish(channel, message)
                receiver_count = int(receiver_count)  # Ensure it's an integer
                
                logger.debug(
                    f"Redis PUBLISH by '{self.client_id}': channel='{channel}', "
                    f"message='{message[:75]}...', receivers={receiver_count}"
                )
                return receiver_count
                
            except Exception as e:
                logger.error(
                    f"Error in Redis PUBLISH operation by '{self.client_id}' for channel '{channel}': {e}",
                    exc_info=True,
                )
                raise

        @asynccontextmanager
        async def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
            """
            Subscribe to a Redis channel with proper lifecycle management.
            
            CRITICAL: This method enables API Gateway instances to listen for 
            user-specific real-time updates from backend services.
            """
            if not self._started:
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

            pubsub = self.client.pubsub()
            try:
                await pubsub.subscribe(channel)
                logger.info(f"Redis SUBSCRIBE by '{self.client_id}': channel='{channel}'")
                yield pubsub
                
            except Exception as e:
                logger.error(
                    f"Error in Redis SUBSCRIBE operation by '{self.client_id}' for channel '{channel}': {e}",
                    exc_info=True
                )
                raise
                
            finally:
                # CRITICAL: Proper cleanup to prevent resource leaks
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()  # Use aclose() instead of deprecated close()
                    logger.info(f"Redis UNSUBSCRIBE by '{self.client_id}': channel='{channel}'")
                except Exception as e:
                    logger.error(
                        f"Error during Redis UNSUBSCRIBE cleanup by '{self.client_id}': {e}",
                        exc_info=True
                    )

        # CRITICAL: Helper method for user-specific channel management
        def get_user_channel(self, user_id: str) -> str:
            """
            Generate standardized user-specific channel name.
            
            Args:
                user_id: The authenticated user's ID
                
            Returns:
                Standardized channel name for the user (e.g., "ws:user_123")
            """
            return f"ws:{user_id}"

        async def publish_user_notification(self, user_id: str, notification: dict) -> int:
            """
            Convenience method to publish JSON notifications to user-specific channels.
            
            Args:
                user_id: The target user's ID
                notification: Dictionary to be serialized as JSON
                
            Returns:
                Number of subscribers that received the notification
            """
            channel = self.get_user_channel(user_id)
            message = json.dumps(notification)
            return await self.publish(channel, message)
    ```

3. **Add Tests for Pub/Sub Functionality**: Ensure the new functionality is properly tested.

    **File**: `services/libs/huleedu_service_libs/tests/test_redis_pubsub.py`

    ```python
    import asyncio
    import json
    import pytest
    from unittest.mock import AsyncMock, patch
    from ..redis_client import RedisClient

    @pytest.mark.asyncio
    async def test_publish_message():
        """Test publishing messages to Redis channels."""
        redis_client = RedisClient("test-client", "redis://localhost:6379")
        
        with patch.object(redis_client, 'client') as mock_client:
            mock_client.publish.return_value = 2  # 2 subscribers received message
            
            result = await redis_client.publish("test:channel", "test message")
            
            assert result == 2
            mock_client.publish.assert_called_once_with("test:channel", "test message")

    @pytest.mark.asyncio
    async def test_user_notification_helper():
        """Test the convenience method for user notifications."""
        redis_client = RedisClient("test-client", "redis://localhost:6379")
        
        with patch.object(redis_client, 'publish') as mock_publish:
            mock_publish.return_value = 1
            
            notification = {"event": "batch_updated", "batch_id": "123"}
            result = await redis_client.publish_user_notification("user_456", notification)
            
            expected_channel = "ws:user_456"
            expected_message = json.dumps(notification)
            
            assert result == 1
            mock_publish.assert_called_once_with(expected_channel, expected_message)

    @pytest.mark.asyncio
    async def test_subscribe_context_manager():
        """Test subscription context manager proper cleanup."""
        redis_client = RedisClient("test-client", "redis://localhost:6379")
        mock_pubsub = AsyncMock()
        
        with patch.object(redis_client, 'client') as mock_client:
            mock_client.pubsub.return_value = mock_pubsub
            
            async with redis_client.subscribe("test:channel") as pubsub:
                assert pubsub == mock_pubsub
                mock_pubsub.subscribe.assert_called_once_with("test:channel")
            
            # Verify cleanup was called
            mock_pubsub.unsubscribe.assert_called_once_with("test:channel")
            mock_pubsub.aclose.assert_called_once()
    ```

**Done When**:

- ✅ The `AtomicRedisClientProtocol` includes fully functional and type-hinted `publish` and `subscribe` methods.
- ✅ The `RedisClient` class implements both methods with proper error handling and resource cleanup.
- ✅ Helper methods for user-specific channels are available (`get_user_channel`, `publish_user_notification`).
- ✅ All existing service library tests pass without regression, confirming backward compatibility.
- ✅ New Pub/Sub functionality is covered by unit tests.
- ✅ The implementation uses `aclose()` instead of deprecated `close()` for proper async resource management.

This implementation provides the foundation for real-time user notifications while maintaining the established patterns and reliability standards of the service library.

### Checkpoint 1.2: Implement New Internal API in Batch Orchestrator Service

**Objective**: Create a new, internal-only HTTP endpoint in BOS to serve the detailed `ProcessingPipelineState` for a given batch. This establishes BOS as the single source of truth for pipeline state and enables the query pattern for other services.

**Affected Files**:

- `services/batch_orchestrator_service/api/batch_routes.py`
- `services/batch_orchestrator_service/protocols.py`
- `services/batch_orchestrator_service/implementations/batch_repository_postgres_impl.py`

**Implementation Steps**:

1. **Add New Route to `batch_routes.py`**: Create a new Quart route for internal queries. This pattern mirrors the existing `/status` endpoint but is prefixed with `/internal` to signify it is not for public consumption and should not be exposed outside our Docker network. The implementation should be lean, delegating the data retrieval logic directly to the repository layer to maintain our clean architecture.

    **File**: `services/batch_orchestrator_service/api/batch_routes.py`

    ```python
    // ... existing imports ...

    # Add this new route to the existing batch_bp Blueprint
    @batch_bp.route("/internal/<batch_id>/pipeline-state", methods=["GET"])
    @inject
    async def get_internal_pipeline_state(
        batch_id: str,
        batch_repo: FromDishka[BatchRepositoryProtocol],
    ) -> Union[Response, tuple[Response, int]]:
        """Internal endpoint to retrieve the full pipeline processing state.
        This endpoint is consumed by the Result Aggregator Service and other
        internal systems, providing a single source of truth for batch state."""
        try:
            # Directly use the existing, tested repository method. This call is highly
            # efficient as it's a primary key lookup on the 'batches' table.
            pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)
            if pipeline_state is None:
                # Return a clear 404 if the batch or its state doesn't exist.
                return jsonify({"error": "Pipeline state not found for batch"}), 404

            # The state is stored as a JSON-compatible dict, so it can be returned directly.
            return jsonify(pipeline_state), 200
        except Exception as e:
            # Log with context for easier debugging if the repository fails.
            current_app.logger.error(f"Error getting internal pipeline state for {batch_id}: {e}", exc_info=True)
            return jsonify({"error": "Failed to get internal pipeline state"}), 500
    ```

**Done When**:

- ✅ The `batch_orchestrator_service` exposes a new, functional, and tested endpoint at `GET /internal/v1/batches/{batch_id}/pipeline-state`.
- ✅ The endpoint correctly retrieves and returns the complete `ProcessingPipelineState` JSON object from the database, leveraging the existing `get_processing_pipeline_state` repository method.

### Checkpoint 1.3: EventEnvelope Compliance and Internal API ✅ COMPLETED

**Implementation Summary**: Fixed BOS technical debt by replacing manual JSON parsing with proper `EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json()` deserialization. Added internal API endpoint `/internal/v1/batches/{batch_id}/pipeline-state` for Result Aggregator Service queries. Updated integration tests to expect `ValidationError` instead of `JSONDecodeError`.

**Code Changes**:

```python
# services/batch_orchestrator_service/implementations/els_batch_phase_outcome_handler.py
envelope = EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json(msg.value)
event_data = envelope.data  # Fully typed object

# services/batch_orchestrator_service/api/batch_routes.py  
@internal_bp.route("/batches/<batch_id>/pipeline-state", methods=["GET"])
pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)
```

**Verified**: All 67 tests pass. EventEnvelope compliance established across all services.

### Checkpoint 1.4: Implement User ID Propagation

**Objective**: Establish a clear, secure path for propagating the authenticated `user_id` from the API Gateway into our backend systems. This is a critical prerequisite for targeted real-time updates.

**Affected Files**:

- `services/api_gateway_service/routers/pipeline_routes.py`
- `common_core/src/common_core/events/client_commands.py`
- `services/batch_orchestrator_service/api_models.py`
- `services/batch_orchestrator_service/implementations/batch_context_operations.py`

**Implementation Steps**:

1. **Update the Command Contract**: Add a `user_id` field to the `ClientBatchPipelineRequestV1` event. This makes user context an explicit part of the command.

    **File**: `common_core/src/common_core/events/client_commands.py`

    ```python
    class ClientBatchPipelineRequestV1(BaseModel):
        batch_id: str
        requested_pipeline: str
        client_correlation_id: uuid.UUID
        user_id: str  # <-- ADD THIS REQUIRED FIELD
    ```

2. **Update BOS Registration Model**: Add an optional `user_id` to the `BatchRegistrationRequestV1` model so it can be persisted.

    **File**: `services/batch_orchestrator_service/api_models.py`

    ```python
    class BatchRegistrationRequestV1(BaseModel):
        # ... existing fields ...
        teacher_name: str = Field(...)
        essay_instructions: str = Field(...)
        user_id: Optional[str] = Field(default=None, description="The ID of the user who owns this batch.") # <-- ADD THIS FIELD
    ```

3. **Update BOS Context Storage**: Modify the `store_batch_context` method in BOS to persist the `user_id` within the `processing_metadata` JSON blob. This makes it retrievable by any process that needs to publish a user-specific notification.

    **File**: `services/batch_orchestrator_service/implementations/batch_context_operations.py`

    ```python
    // In class BatchContextOperations, method store_batch_context
        # ...
        if batch is None:
            # Create new batch record
            # The full registration_data, which now includes user_id, is stored.
            batch = Batch(
                id=batch_id,
                #...
                processing_metadata=registration_data.model_dump(),
            )
            session.add(batch)
        else:
            # Update existing batch with context
            stmt = (
                update(Batch)
                .where(Batch.id == batch_id)
                .values(
                    # ...
                    # The full registration_data, including user_id, is stored here too.
                    processing_metadata=registration_data.model_dump(),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await session.execute(stmt)
    ```

**Done When**:

- ✅ The `user_id` is part of the `ClientBatchPipelineRequestV1` contract.
- ✅ The API Gateway is capable of populating this field.
- ✅ The Batch Orchestrator Service correctly persists the `user_id` as part of the batch context.

### Checkpoint 1.5: Create and Implement the `result_aggregator_service` (Revised + Hardened)

**Objective**: Build the aggregator service to use the query pattern with critical production hardening based on architect feedback. This service acts as a performance-enhancing cache and materialized view, shielding our frontend-facing gateway from the complexities of the internal event bus.

**Affected Files**:

- New service directory: `services/result_aggregator_service/`
- `docker-compose.yml`, `docker-compose.infrastructure.yml`, `docker-compose.services.yml`

**Implementation Steps**:

1. **Create Service Structure and DB Schema with Security**: Create the new service directory `services/result_aggregator_service/`. Its structure must follow our standard Quart service pattern, as exemplified by `services/batch_orchestrator_service/`. In the new `models_db.py`, define the `BatchStatusView` model **with explicit `user_id` column** for fast ownership lookups without querying BOS.

    **File**: `services/result_aggregator_service/models_db.py`

    ```python
    from sqlalchemy import Column, String, DateTime, Text
    from sqlalchemy.ext.declarative import declarative_base
    from datetime import datetime

    Base = declarative_base()

    class BatchStatusView(Base):
        """Materialized view of batch status for fast client queries."""
        __tablename__ = "batch_status_view"

        batch_id = Column(String(255), primary_key=True)
        user_id = Column(String(255), nullable=False, index=True)  # CRITICAL: Explicit user_id for ownership checks
        pipeline_state = Column(Text, nullable=False)  # JSON blob
        last_updated = Column(DateTime, nullable=False, default=datetime.utcnow)
    ```

2. **Implement Hardened `kafka_consumer.py`**: The consumer now includes critical production patterns: manual commits, proper timeouts, retry logic, and comprehensive error handling.

    **File**: `services/result_aggregator_service/kafka_consumer.py`

    ```python
    import asyncio
    import json
    from typing import Any
    from aiohttp import ClientSession, ClientTimeout
    from tenacity import retry, stop_after_attempt, wait_exponential
    from huleedu_service_libs.logging_utils import create_service_logger
    from huleedu_service_libs.kafka_client import KafkaBus

    logger = create_service_logger("result_aggregator.kafka_consumer")

    class ResultAggregatorKafkaConsumer:
        def __init__(self, 
                     repository: ResultRepositoryProtocol, 
                     http_session: ClientSession, 
                     settings: Settings):
            self.repository = repository
            self.http_session = http_session
            self.settings = settings
            # CRITICAL: Manual commits for data consistency (Architect Feedback #11)
            self.kafka_consumer = None  # Will be configured with enable_auto_commit=False

        async def start_consuming(self):
            """Start consuming with manual commit pattern for data consistency."""
            topics = [
                "huleedu.els.batch_phase.outcome.v1"
            ]
            
            # CRITICAL: Manual commits disabled for at-least-once processing
            consumer_config = {
                "enable_auto_commit": False,  # Architect Feedback #11
                "auto_offset_reset": "earliest",
                "group_id": "result-aggregator-service"
            }
            
            async for msg in self._consume_messages(topics, consumer_config):
                try:
                    await self._handle_message(msg)
                    # CRITICAL: Only commit after successful processing
                    await self.kafka_consumer.commit()
                    logger.info(f"Successfully processed and committed message for batch {msg.key}")
                except Exception as e:
                    logger.error(f"Failed to process message: {e}", exc_info=True)
                    # Do not commit - message will be reprocessed

        async def _handle_message(self, msg: Any):
            """Handle ELSBatchPhaseOutcomeV1 events with BOS state query and hardened error handling."""
            try:
                envelope = EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json(msg.value)
                event_data = envelope.data
                batch_id = event_data.batch_id
                correlation_id = envelope.correlation_id

                logger.info(f"Processing phase outcome for batch '{batch_id}', correlation_id='{correlation_id}'")

                # CRITICAL: Query BOS with timeout and retry (Architect Feedback #6)
                bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
                try:
                    full_pipeline_state = await self._fetch_state_with_retry(bos_url, correlation_id)
                except Exception as e:
                    logger.error(
                        f"Failed to query BOS for batch '{batch_id}' after retries, correlation_id='{correlation_id}': {e}",
                        exc_info=True
                    )
                    raise  # Will prevent Kafka commit, enabling reprocessing

                # CRITICAL: Store with explicit user_id for ownership checks (Architect Feedback #7)
                user_id = full_pipeline_state.get("user_id")
                if not user_id:
                    logger.warning(f"No user_id found in pipeline state for batch '{batch_id}'")

                await self.repository.upsert_batch_status(
                    batch_id=batch_id,
                    pipeline_state_update=full_pipeline_state,
                    user_id=user_id,
                )
                
                # CRITICAL: Comprehensive logging for traceability (Architect Feedback #9)
                logger.info(
                    f"Successfully updated aggregator view: batch_id='{batch_id}', "
                    f"user_id='{user_id}', correlation_id='{correlation_id}'"
                )
                    
            except Exception as e:
                logger.error(f"Error handling message from {msg.topic}: {e}", exc_info=True)
                raise  # Re-raise to prevent commit

        @retry(
            stop=stop_after_attempt(3), 
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        async def _fetch_state_with_retry(self, url: str, correlation_id: str = None) -> dict:
            """Fetch state from BOS with timeout and retry logic (Architect Feedback #6)."""
            # CRITICAL: Explicit timeout to prevent indefinite hangs
            timeout = ClientTimeout(total=self.settings.BOS_QUERY_TIMEOUT_SECONDS)
            
            async with self.http_session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    state_data = await response.json()
                    logger.debug(f"Successfully fetched state from BOS: correlation_id='{correlation_id}'")
                    return state_data
                elif response.status == 404:
                    logger.warning(f"Batch not found in BOS: {url}, correlation_id='{correlation_id}'")
                    return {}  # Return empty state for 404s
                else:
                    response.raise_for_status()  # Will trigger tenacity retry
    ```

3. **Implement Secured Internal API Endpoint**: The aggregator's API must enforce ownership checks to prevent users from accessing other users' batch data.

    **File**: `services/result_aggregator_service/api/query_routes.py`

    ```python
    from quart import Blueprint, jsonify, Response
    from quart_dishka import inject
    from dishka import FromDishka
    from ..protocols import ResultRepositoryProtocol 

    query_bp = Blueprint("query_routes", __name__, url_prefix="/internal/v1")

    @query_bp.route("/batches/<batch_id>/status", methods=["GET"])
    @inject
    async def get_aggregated_batch_status(
        batch_id: str,
        repo: FromDishka[ResultRepositoryProtocol]
    ) -> tuple[Response, int]:
        """
        Get aggregated batch status with explicit user_id for ownership enforcement.
        
        CRITICAL: This endpoint returns the user_id so the API Gateway can enforce
        ownership checks without additional BOS queries (Architect Feedback #1, #7).
        """
        try:
            status_view = await repo.get_batch_status(batch_id)
            if not status_view:
                return jsonify({"error": "Batch status not found"}), 404

            # CRITICAL: Return user_id for Gateway ownership enforcement
            response_data = {
                "batch_id": status_view.batch_id,
                "user_id": status_view.user_id,  # ESSENTIAL for ownership checks
                "pipeline_state": status_view.pipeline_state,
                "last_updated": status_view.last_updated.isoformat(),
            }
            
            return jsonify(response_data), 200
            
        except Exception as e:
            logger.error(f"Error retrieving batch status for {batch_id}: {e}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
    ```

4. **Add Graceful Shutdown Hooks**: Implement proper resource cleanup to prevent hangs and resource leaks during deployment.

    **File**: `services/result_aggregator_service/app.py`

    ```python
    from quart import Quart
    from .startup_setup import initialize_service, cleanup_service

    app = Quart(__name__)

    @app.before_serving
    async def startup():
        """Initialize service resources."""
        await initialize_service(app)

    @app.after_serving  
    async def shutdown():
        """CRITICAL: Graceful shutdown with proper resource cleanup (Architect Feedback #4)."""
        await cleanup_service(app)
        logger.info("Result Aggregator Service shutdown complete")
    ```

    **File**: `services/result_aggregator_service/startup_setup.py`

    ```python
    async def cleanup_service(app: Quart):
        """Clean up service resources to prevent leaks during deployment."""
        try:
            # Close HTTP session
            if hasattr(app, 'http_session'):
                await app.http_session.close()
                logger.info("HTTP session closed")
                
            # Stop Kafka consumer
            if hasattr(app, 'kafka_consumer'):
                await app.kafka_consumer.stop()
                logger.info("Kafka consumer stopped")
                
            # Close DI container
            if hasattr(app, 'di_container'):
                await app.di_container.close()
                logger.info("DI container closed")
                
        except Exception as e:
            logger.error(f"Error during service cleanup: {e}", exc_info=True)
    ```

**Configuration Updates**:

**File**: `services/result_aggregator_service/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # CRITICAL: Timeout configuration (Architect Feedback #6)
    BOS_QUERY_TIMEOUT_SECONDS: int = Field(default=5, description="Timeout for BOS state queries")
    BOS_QUERY_RETRY_ATTEMPTS: int = Field(default=3, description="Number of retry attempts for BOS queries")
    
    # Initial batch seeding strategy (Architect Feedback #8)
    HANDLE_MISSING_BATCHES: str = Field(default="query_bos", description="Strategy for 404 batches: 'query_bos' or 'return_404'")
```

**Done When**:

- ✅ The `result_aggregator_service` is fully containerized and production-hardened.
- ✅ Its consumer correctly processes ELSBatchPhaseOutcomeV1 events with manual Kafka commits for data consistency.
- ✅ HTTP queries to BOS include proper timeouts and retry logic to prevent indefinite hangs.
- ✅ The aggregator's database includes explicit `user_id` column for fast ownership lookups.
- ✅ The aggregator's API returns `user_id` so the Gateway can enforce ownership without additional queries.
- ✅ Graceful shutdown hooks ensure proper resource cleanup during deployments.
- ✅ Comprehensive logging includes `batch_id`, `user_id`, and `correlation_id` for full traceability.

This hardened implementation addresses the architect's critical feedback while maintaining the architectural vision of the query pattern.
