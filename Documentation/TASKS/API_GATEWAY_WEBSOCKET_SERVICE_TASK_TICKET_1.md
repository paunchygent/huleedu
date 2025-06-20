# Implementation Guide: HuleEdu Client Interface Layer (1/3)

This document provides a step-by-step implementation plan for the foundational components of the client interface layer, revised to implement the architecturally pure "thin event" pattern from the start.

## Part 1: Foundational Layer (BOS API, Thin Events & Result Aggregator)

This part is now re-ordered and expanded. It covers the critical prerequisite of creating a new internal API endpoint in the Batch Orchestrator Service (BOS), redefining the core event contract, and then building the `result_aggregator_service` to use these new components. This sequence is mandatory to ensure that the services built in Part 2 and 3 have the necessary infrastructure to function correctly.

### Checkpoint 1.1: Extend Shared Redis Client for Pub/Sub

**Objective**: Enhance our existing `RedisClient` in `huleedu-service-libs` to support the WebSocket backplane. This extension is foundational for the real-time communication required by the frontend, enabling a responsive user experience.

**Context and Rationale**:
Our real-time architecture depends on a "backplane"—a messaging system that allows multiple, independent instances of our API Gateway to communicate with backend services without knowing about each other. Redis Pub/Sub is the industry-standard solution for this. It provides a lightweight, high-speed channel where backend services can "publish" UI update events. The API Gateway instances will "subscribe" to these channels and forward the messages to the specific WebSocket clients they are connected to. This decouples the stateful WebSocket connections from our stateless backend, which is essential for horizontal scaling.

**Affected Files**:
- `services/libs/huleedu_service_libs/redis_client.py`
- `services/libs/huleedu_service_libs/protocols.py`

**Implementation Steps**:
1.  **Update `AtomicRedisClientProtocol`**: Add `publish` and `subscribe` methods to the protocol definition. This ensures any service depending on this protocol can be type-checked correctly, maintaining our commitment to type safety.

    **File**: `services/libs/huleedu_service_libs/protocols.py`

    ```python
    // ... existing protocol code ...
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

2.  **Implement `publish` and `subscribe` in `RedisClient`**: Add the concrete implementations to the main client class. It is critical to use `aclose()` instead of the deprecated `close()` to ensure the underlying connection pool is managed correctly by the `redis-py` async library, preventing resource leaks.

    **File**: `services/libs/huleedu_service_libs/redis_client.py`

    ```python
    // ... existing RedisClient class code ...

        async def publish(self, channel: str, message: str) -> int:
            if not self._started:
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
            try:
                receiver_count = await self.client.publish(channel, message)
                # We expect receiver_count to be an int, but cast for safety.
                receiver_count = int(receiver_count) 
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
            if not self._started:
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

            pubsub = self.client.pubsub()
            try:
                await pubsub.subscribe(channel)
                logger.info(f"Redis SUBSCRIBE by '{self.client_id}': channel='{channel}'")
                yield pubsub
            finally:
                # This gracefully unsubscribes and cleans up the specific pubsub connection
                # without affecting the main client connection pool.
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                logger.info(f"Redis UNSUBSCRIBE by '{self.client_id}': channel='{channel}'")
    ```

**Done When**:
- ✅ The `RedisClient` class and its corresponding protocol include fully functional and type-hinted `publish` and `subscribe` methods.
- ✅ All existing service library tests pass without regression, confirming that the changes have not impacted the client's original idempotency-related functionality.

### Checkpoint 1.2: Implement New Internal API in Batch Orchestrator Service

**Objective**: Create a new, internal-only HTTP endpoint in BOS to serve the detailed `ProcessingPipelineState` for a given batch. This is the cornerstone of the thin-event approach, establishing BOS as the single source of truth for pipeline state and allowing other services to query it without requiring "fat events."

**Affected Files**:
- `services/batch_orchestrator_service/api/batch_routes.py`
- `services/batch_orchestrator_service/protocols.py`
- `services/batch_orchestrator_service/implementations/batch_repository_postgres_impl.py`

**Implementation Steps**:
1.  **Add New Route to `batch_routes.py`**: Create a new Quart route for internal queries. This pattern mirrors the existing `/status` endpoint but is prefixed with `/internal` to signify it is not for public consumption and should not be exposed outside our Docker network. The implementation should be lean, delegating the data retrieval logic directly to the repository layer to maintain our clean architecture.

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

### Checkpoint 1.3: Redefine `ELSBatchPhaseOutcomeV1` as a Thin Event

**Objective**: Modify the core event contract to remove the large `pipeline_state` payload, in adherence with our "Thin Events" principle (`030-event-driven-architecture-eda-standards.mdc`). This change is critical for long-term performance and scalability of our Kafka cluster by reducing message size and consumer load.

**Affected Files**:
- `common_core/src/common_core/events/els_bos_events.py`
- `services/essay_lifecycle_service/implementations/batch_phase_coordinator_impl.py` (publisher)
- `services/batch_orchestrator_service/implementations/els_batch_phase_outcome_handler.py` (consumer)

**Implementation Steps**:
1.  **Update the Pydantic Model**: Remove fields that can be queried from the new BOS endpoint, leaving only the essential notification data. The `processed_essays` list is kept because it contains the output `text_storage_ids`, which are essential context for the next phase, not just a reflection of state.

    **File**: `common_core/src/common_core/events/els_bos_events.py`

    ```python
    // ... imports ...
    class ELSBatchPhaseOutcomeV1(BaseModel):
        """
        [REVISED] Event published by ELS to notify BOS about the completion of a 
        processing phase for a batch. This is a thin event; the full updated 
        state must be queried from the authoritative service (BOS).
        """
        batch_id: str = Field(...)
        phase_name: str = Field(...)
        phase_status: str = Field(...)
        # This field remains critical, as it provides the output storage IDs
        # needed as input for the *next* phase. This is essential context.
        processed_essays: List[EssayProcessingInputRefV1] = Field(...)
        failed_essay_ids: List[str] = Field(...)
        correlation_id: Optional[UUID] = Field(None)

    ```

**Done When**:
- ✅ The `ELSBatchPhaseOutcomeV1` model in `common_core` is updated to reflect the thin event structure.
- ✅ The ELS service is updated to publish this new, leaner event, and the BOS service is updated to consume it.
- ✅ All relevant contract tests are updated and pass, verifying the new event structure.

### Checkpoint 1.4: Implement User ID Propagation

**Objective**: Establish a clear, secure path for propagating the authenticated `user_id` from the API Gateway into our backend systems. This is a critical prerequisite for targeted real-time updates.

**Affected Files**:
- `services/api_gateway_service/routers/pipeline_routes.py`
- `common_core/src/common_core/events/client_commands.py`
- `services/batch_orchestrator_service/api_models.py`
- `services/batch_orchestrator_service/implementations/batch_context_operations.py`

**Implementation Steps**:
1.  **Update the Command Contract**: Add a `user_id` field to the `ClientBatchPipelineRequestV1` event. This makes user context an explicit part of the command.

    **File**: `common_core/src/common_core/events/client_commands.py`

    ```python
    class ClientBatchPipelineRequestV1(BaseModel):
        batch_id: str
        requested_pipeline: str
        client_correlation_id: uuid.UUID
        user_id: str  # <-- ADD THIS REQUIRED FIELD
    ```

2.  **Update BOS Registration Model**: Add an optional `user_id` to the `BatchRegistrationRequestV1` model so it can be persisted.

    **File**: `services/batch_orchestrator_service/api_models.py`

    ```python
    class BatchRegistrationRequestV1(BaseModel):
        # ... existing fields ...
        teacher_name: str = Field(...)
        essay_instructions: str = Field(...)
        user_id: Optional[str] = Field(default=None, description="The ID of the user who owns this batch.") # <-- ADD THIS FIELD
    ```

3.  **Update BOS Context Storage**: Modify the `store_batch_context` method in BOS to persist the `user_id` within the `processing_metadata` JSON blob. This makes it retrievable by any process that needs to publish a user-specific notification.

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

### Checkpoint 1.5: Create and Implement the `result_aggregator_service` (Revised)

**Objective**: Build the aggregator service to use the new "thin event + query" pattern. This service acts as a performance-enhancing cache and a materialized view, shielding our frontend-facing gateway from the complexities of the internal event bus.

**Affected Files**:
- New service directory: `services/result_aggregator_service/`
- `docker-compose.yml`, `docker-compose.infrastructure.yml`, `docker-compose.services.yml`

**Implementation Steps**:
1.  **Create Service Structure and DB Schema**: Create the new service directory `services/result_aggregator_service/`. Its structure must follow our standard Quart service pattern, as exemplified by `services/batch_orchestrator_service/`. This includes creating `app.py`, `config.py`, `di.py`, `models_db.py`, and `api/` directories. In the new `models_db.py`, define the `BatchStatusView` model as specified in the rationale.

2.  **Implement `kafka_consumer.py` (Revised Logic)**: The consumer now has an additional step: it must call the new BOS internal API to fetch the full state after being notified by the thin event. This ensures the aggregator always has the most current and complete data, making it a reliable read model. It must also include retry logic to handle cases where BOS might be temporarily unavailable.

    **File**: `services/result_aggregator_service/kafka_consumer.py`

    ```python
    // ... imports, including repository, aiohttp.ClientSession, and tenacity for retries ...

    class ResultAggregatorKafkaConsumer:
        def __init__(self, ..., http_session: ClientSession, repository: ResultRepositoryProtocol, settings: Settings):
            self.http_session = http_session
            self.repository = repository
            self.settings = settings
            // ...

        async def _handle_message(self, msg: Any):
            envelope = EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json(msg.value)
            event_data = envelope.data
            batch_id = event_data.batch_id

            # 1. Receive THIN event notification
            logger.info(f"Received thin event BatchPhaseOutcome for batch '{batch_id}'")

            # 2. Query BOS (the source of truth) for the FULL, up-to-date state.
            # This operation includes retry logic for resilience.
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
            try:
                full_pipeline_state = await self._fetch_state_with_retry(bos_url)
            except Exception as e:
                logger.error(f"Failed to query BOS for state of batch '{batch_id}' after retries: {e}", exc_info=True)
                # Do not proceed. The message will be retried by the consumer loop later.
                raise e

            # 3. Persist the authoritative state to the aggregator's database.
            await self.repository.upsert_batch_status(
                batch_id=batch_id,
                pipeline_state_update=full_pipeline_state,
            )
            logger.info(f"Successfully updated aggregator view for batch '{batch_id}' with fresh state from BOS.")

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
        async def _fetch_state_with_retry(self, url: str) -> dict:
             async with self.http_session.get(url) as response:
                 response.raise_for_status() # Will trigger tenacity retry on 4xx/5xx
                 return await response.json()
    ```

3.  **Implement Internal API Endpoint**: The aggregator's own API must be implemented using Quart. It simply serves the data it has stored.

    **File**: `services/result_aggregator_service/api/query_routes.py`

    ```python
    # Using Quart, our internal service standard.
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
        status_view = await repo.get_batch_status(batch_id)
        if not status_view:
            return jsonify({"error": "Batch status not found"}), 404

        return jsonify({
            "batch_id": status_view.batch_id,
            "pipeline_state": status_view.pipeline_state,
            "last_updated": status_view.last_updated.isoformat(),
        }), 200
    ```

**Done When**:
- ✅ The `result_aggregator_service` is fully containerized and functional.
- ✅ Its consumer correctly processes the new thin event and successfully queries the new BOS internal API to fetch the full, authoritative state.
- ✅ The fetched state is correctly persisted to the aggregator's own PostgreSQL database.
- ✅ The aggregator's internal API correctly serves the persisted state to its clients (i.e., the API Gateway).

This revised Part 1 establishes a more robust and architecturally pure foundation. Part 2 and 3 will now build upon this, but their own implementation details remain largely unchanged as their external contracts are unaffected.