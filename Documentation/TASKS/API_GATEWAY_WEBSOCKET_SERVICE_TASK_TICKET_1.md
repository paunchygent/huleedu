# Implementation Guide: HuleEdu Client Interface Layer (1/3)

This document provides a step-by-step implementation plan for the foundational components of the client interface layer.

## Part 1: Foundational Layer (BOS API, Query Pattern & Result Aggregator)

This part covers the critical prerequisite of creating a new internal API endpoint in the Batch Orchestrator Service (BOS), fixing event parsing compliance, and building the `result_aggregator_service` to use these new components. This sequence is mandatory to ensure that the services built in Part 2 and 3 have the necessary infrastructure to function correctly.

### Checkpoint 1.1: Extend Shared Redis Client for Pub/Sub ✅ COMPLETED

**Implementation Summary**: Extended `AtomicRedisClientProtocol` with `publish()`, `subscribe()`, `get_user_channel()`, and `publish_user_notification()` methods. Updated BOS and ELS DI containers to provide `AtomicRedisClientProtocol` instead of basic `RedisClientProtocol`. Established standardized user channel format `ws:{user_id}` for WebSocket backplane communication.

**Core Implementation**:

- **Protocol Extension**: Added pub/sub methods to `AtomicRedisClientProtocol` in `services/libs/huleedu_service_libs/protocols.py`
- **Redis Client**: Implemented async context manager `subscribe()` with proper cleanup using `aclose()`, `publish()` with receiver count logging
- **Service Integration**: Updated `services/batch_orchestrator_service/di.py` and `services/essay_lifecycle_service/di.py` to inject `AtomicRedisClientProtocol`
- **Test Coverage**: 18 service library tests + 5 BOS tests + 5 ELS tests all passing

**Usage Pattern**:

```python
# Backend services publish user-specific updates
await redis_client.publish_user_notification(
    user_id, "batch_status_update", {"batch_id": "123", "status": "completed"}
)

# API Gateway subscribes to user channels
async with redis_client.subscribe("ws:user_123") as pubsub:
    async for message in pubsub.listen():
        # Forward to WebSocket client
```

**Ready for**: API Gateway implementation can now subscribe to user-specific channels while backend services publish real-time updates.

### Checkpoint 1.2: Implement New Internal API in Batch Orchestrator Service ✅ COMPLETED

**Implementation Summary**: Added internal API endpoint `GET /internal/v1/batches/{batch_id}/pipeline-state` to BOS for Result Aggregator Service queries. Endpoint uses existing `get_processing_pipeline_state()` repository method, returns complete ProcessingPipelineState JSON with user_id for ownership checks, and provides proper 404/500 error handling.

**Core Implementation**:

- **Internal Blueprint**: Added `internal_bp` to `services/batch_orchestrator_service/api/batch_routes.py` with `/internal/v1/batches` prefix
- **Pipeline State Query**: Direct repository method call for efficient primary key lookup on batches table  
- **Response Format**: Returns `{batch_id, pipeline_state, user_id}` structure for Result Aggregator consumption
- **Error Handling**: 404 for non-existent batches, 500 with logging for repository failures

**Verification**: Live endpoint testing confirmed proper JSON response with complete pipeline state data and correct HTTP status codes (200/404).

**Ready for**: Result Aggregator Service implementation can now query BOS as single source of truth for batch pipeline state.

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

### Checkpoint 1.4: Implement User ID Propagation ✅ COMPLETED

**⚠️ PLANNING ANALYSIS COMPLETED ✅**

**Critical Findings**: User ID propagation requires significant prerequisite infrastructure that is not currently implemented. The checkpoint cannot be completed as specified without first building the foundational API Gateway components.

**Architectural Gaps Identified**:

1. **Missing API Gateway Router**: `pipeline_routes.py` referenced in task doesn't exist
2. **No Authentication System**: JWT validation middleware not implemented  
3. **No Event Publishing**: API Gateway lacks Kafka producer capability
4. **Incomplete Integration**: BOS internal API expects user_id but model lacks the field

**Prerequisite Implementation Required**: Before user_id propagation can work, the API Gateway service needs complete foundational architecture following FastAPI + Dishka patterns established in the codebase.

**✅ IMPLEMENTATION COMPLETED**

**Data Model Changes**: Successfully implemented user_id propagation for lean registration pattern:

- **`ClientBatchPipelineRequestV1`**: Added required `user_id` field with validation (min_length=1, max_length=255)
- **`BatchRegistrationRequestV1`**: Only captures essential upload data: `user_id` (from JWT), `course_code`, `essay_instructions`
- **Batch Context Storage**: `store_batch_context()` persists user_id for ownership validation throughout processing pipeline
- **Internal API Integration**: BOS `/internal/v1/batches/{batch_id}/pipeline-state` endpoint returns user_id for ownership checks
- **Educational Context Deferred**: Teacher names, class designation obtained from Class Management Service when processing starts

**Validation Results**:

- ✅ All 64 common_core tests pass
- ✅ All 8 BOS integration tests pass  
- ✅ User_id field enables complete ownership validation and data isolation
- ✅ Lean registration maintains single source of truth principles
- ✅ Processing services get teacher context (`teacher_first_name`, `teacher_last_name`) from Class Management Service based on user_id

**Remaining Work**: API Gateway infrastructure (authentication, routing, event publishing) must be implemented before full user_id propagation flow can be tested end-to-end.

---

## 🔗 **Connected Implementation: Enhanced Features**

**NEXT IMPLEMENTATION PHASE**: After completing Checkpoint 1.4 (User ID Propagation), the enhanced file and class management capabilities should be implemented following the comprehensive plan outlined in:

📋 **[CLIENT_RETRY_FRAMEWORK_IMPLEMENTATION.md]** (**COMPLETED**)
📋 **[ENHANCED_CLASS_AND_FILE_MANAGEMENT_IMPLEMENTATION.md](ENHANCED_CLASS_AND_FILE_MANAGEMENT_IMPLEMENTATION.md)**

This connected implementation provides:

- Enhanced batch registration with course validation
- File management with batch state validation
- Class Management Service for student/class relationships
- Student parsing integration with confidence scoring
- Real-time WebSocket updates for all operations

The enhanced features build directly on the User ID Propagation foundation to provide comprehensive educational management capabilities while maintaining architectural integrity.

---

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
