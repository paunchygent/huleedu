# Implementation Guide: HuleEdu Client Interface Layer (3/3)

This document provides the final implementation steps for the client interface layer, focusing on read queries, real-time updates, and modifications to existing services to support the new frontend architecture.

## ✅ **BLOCKING DEPENDENCY RESOLVED - REFACTORING COMPLETED**

**✅ FOUNDATION READY: This task can now proceed with:**

📋 **[LEAN_BATCH_REGISTRATION_REFACTORING.md](LEAN_BATCH_REGISTRATION_REFACTORING.md)** - **COMPLETED**

**Result**: WebSocket events and backend modifications can now be implemented with proper service boundaries where educational context is managed by Class Management Service.

## Part 3: Query Endpoints, WebSocket Layer & Backend Modifications

This part completes the `api_gateway_service` by adding the read-path and real-time components. It also details the required changes in our existing backend services to publish data to the new WebSocket backplane.

### Checkpoint 3.1: Implement Query Endpoint for Batch Status (Secured)

**Objective**: Implement the `GET /v1/batches/{batch_id}/status` endpoint in the API Gateway with critical security enforcement. This endpoint serves as the "Hydrate" mechanism for the frontend while ensuring users can only access their own batch data.

**Affected Files**:

- `services/api_gateway_service/routers/status_routes.py` (new)
- `services/api_gateway_service/main.py` (modification)
- `services/api_gateway_service/config.py` (modification)

**Implementation Steps**:

1. **Implement the Secured Status Endpoint Router**: This router enforces ownership checks and handles all edge cases properly.

    **File**: `services/api_gateway_service/routers/status_routes.py`

    ```python
    from fastapi import APIRouter, Depends, HTTPException, status, Request
    from dishka.integrations.fastapi import FromDishka
    from aiohttp import ClientSession, ClientResponseError, ClientTimeout
    from huleedu_service_libs.logging_utils import create_service_logger
    from ..config import settings
    from ..middleware.rate_limit_middleware import limiter
    from .. import auth

    router = APIRouter()
    logger = create_service_logger("api_gateway.status_routes")

    @router.get("/batches/{batch_id}/status")
    @limiter.limit("50/minute")  # Higher limit for read operations, but still protected
    async def get_batch_status(
        request: Request,  # Required for rate limiting
        batch_id: str,
        user_id: str = Depends(auth.get_current_user_id),
        http_session: FromDishka[ClientSession],
    ):
        """
        Get batch status with strict ownership enforcement.
        
        CRITICAL: Implements architect feedback #1 for ownership checks.
        This prevents any authenticated user from accessing another user's batch data.
        """
        correlation_id = getattr(request.state, 'correlation_id', None) or str(uuid4())
        
        logger.info(
            f"Batch status request: batch_id='{batch_id}', user_id='{user_id}', "
            f"correlation_id='{correlation_id}'"
        )

        aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{batch_id}/status"

        try:
            # CRITICAL: Use configured timeout to prevent indefinite hangs (Architect Feedback #6)
            async with http_session.get(aggregator_url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # CRITICAL: Enforce ownership check (Architect Feedback #1)
                    batch_owner_id = data.get("user_id")
                    if not batch_owner_id:
                        logger.warning(
                            f"Batch status missing user_id: batch_id='{batch_id}', "
                            f"requesting_user='{user_id}', correlation_id='{correlation_id}'"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Batch ownership information unavailable"
                        )
                    
                    if batch_owner_id != user_id:
                        logger.warning(
                            f"Ownership violation: batch_id='{batch_id}', "
                            f"owner='{batch_owner_id}', requester='{user_id}', "
                            f"correlation_id='{correlation_id}'"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN, 
                            detail="Access denied: You don't have permission to view this batch"
                        )
                    
                    # CRITICAL: Remove internal user_id from client response
                    client_response = {
                        "batch_id": data["batch_id"],
                        "pipeline_state": data["pipeline_state"],
                        "last_updated": data["last_updated"],
                        "status": "available"
                    }
                    
                    logger.info(
                        f"Batch status retrieved successfully: batch_id='{batch_id}', "
                        f"user_id='{user_id}', correlation_id='{correlation_id}'"
                    )
                    
                    return client_response
                    
                elif response.status == 404:
                    # Handle initial seeding strategy (Architect Feedback #8)
                    if settings.HANDLE_MISSING_BATCHES == "query_bos":
                        logger.info(
                            f"Batch not in aggregator, checking BOS: batch_id='{batch_id}', "
                            f"user_id='{user_id}', correlation_id='{correlation_id}'"
                        )
                        
                        # Fallback to BOS for initial state
                        bos_url = f"{settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
                        try:
                            async with http_session.get(bos_url) as bos_response:
                                if bos_response.status == 200:
                                    bos_data = await bos_response.json()
                                    
                                    # CRITICAL: Enforce ownership on BOS data too
                                    bos_user_id = bos_data.get("user_id")
                                    if bos_user_id != user_id:
                                        raise HTTPException(
                                            status_code=status.HTTP_403_FORBIDDEN,
                                            detail="Access denied: You don't have permission to view this batch"
                                        )
                                    
                                    # Return BOS data in client format
                                    return {
                                        "batch_id": batch_id,
                                        "pipeline_state": bos_data,
                                        "last_updated": bos_data.get("updated_at", "unknown"),
                                        "status": "pending_aggregation"
                                    }
                                elif bos_response.status == 404:
                                    raise HTTPException(
                                        status_code=status.HTTP_404_NOT_FOUND,
                                        detail="Batch not found"
                                    )
                                else:
                                    bos_response.raise_for_status()
                                    
                        except ClientResponseError as e:
                            logger.error(
                                f"BOS fallback failed: batch_id='{batch_id}', "
                                f"user_id='{user_id}', correlation_id='{correlation_id}', error='{e}'"
                            )
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Backend services temporarily unavailable"
                            )
                    else:
                        # Return 404 immediately without BOS fallback
                        logger.info(
                            f"Batch not found in aggregator: batch_id='{batch_id}', "
                            f"user_id='{user_id}', correlation_id='{correlation_id}'"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Batch not found or not yet processed"
                        )
                        
                else:
                    logger.error(
                        f"Aggregator service error: status={response.status}, "
                        f"batch_id='{batch_id}', user_id='{user_id}', correlation_id='{correlation_id}'"
                    )
                    response.raise_for_status()
                    
        except ClientResponseError as e:
            if e.status == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Batch not found"
                )
            else:
                logger.error(
                    f"HTTP error querying aggregator: batch_id='{batch_id}', "
                    f"user_id='{user_id}', correlation_id='{correlation_id}', error='{e}'"
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Result aggregator service is temporarily unavailable"
                )
                
        except Exception as e:
            logger.error(
                f"Unexpected error retrieving batch status: batch_id='{batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}', error='{e}'",
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    ```

2. **Update Configuration for Initial Batch Seeding Strategy**:

    **File**: `services/api_gateway_service/config.py`

    ```python
    class Settings(BaseSettings):
        # ... existing settings ...
        
        # Service URLs
        RESULT_AGGREGATOR_URL: str = Field(
            default="http://result_aggregator_service:8000",
            description="Result Aggregator Service base URL"
        )
        BOS_URL: str = Field(
            default="http://batch_orchestrator_service:8000",
            description="Batch Orchestrator Service base URL for fallback queries"
        )
        
        # Initial batch seeding strategy (Architect Feedback #8)
        HANDLE_MISSING_BATCHES: str = Field(
            default="query_bos",
            description="Strategy for 404 batches: 'query_bos' or 'return_404'"
        )
    ```

3. **Update `main.py` to Register the New Router**:

    **File**: `services/api_gateway_service/main.py`

    ```python
    // ... existing imports ...
    from .routers import pipeline_routes, status_routes  # Add status_routes

    // ... app setup ...

    // Register Routers
    app.include_router(pipeline_routes.router, prefix="/v1", tags=["Pipelines"])
    app.include_router(status_routes.router, prefix="/v1", tags=["Status"])  # Add this line
    ```

**Done When**:

- ✅ **CRITICAL**: Ownership checks are enforced - users can only access their own batch data (Architect Feedback #1).
- ✅ A `GET` request to `/v1/batches/{batch_id}/status` with valid JWT returns batch status only for owned batches.
- ✅ The endpoint returns `403 Forbidden` when users try to access batches they don't own.
- ✅ The endpoint returns `404 Not Found` when batches don't exist in the aggregator.
- ✅ Fallback to BOS is implemented for initial batch seeding with configurable strategy (Architect Feedback #8).
- ✅ HTTP timeouts prevent indefinite hangs when querying backend services (Architect Feedback #6).
- ✅ Rate limiting protects against query abuse while allowing reasonable read volumes.
- ✅ Comprehensive logging includes `batch_id`, `user_id`, and `correlation_id` for full traceability (Architect Feedback #9).
- ✅ The `user_id` is not exposed in client responses (internal ownership data only).

This secured implementation closes the major security gap identified by the architect while providing a robust query mechanism for the frontend.

### Checkpoint 3.2: Implement WebSocket Endpoint and Redis Backplane (Enhanced)

**Objective**: Implement the real-time "Update" mechanism by creating the WebSocket endpoint and its Redis Pub/Sub listener, with enhanced support for class management, file operations, and student associations.

**Affected Files**:

- `services/api_gateway_service/routers/websocket_routes.py` (new)
- `services/api_gateway_service/main.py` (modification)
- `services/api_gateway_service/di.py` (modification)

**Implementation Steps**:

1. **Update DI to Provide the Redis Client**: The gateway needs the extended `AtomicRedisClientProtocol` to subscribe to channels.

    **File**: `services/api_gateway_service/di.py`

    ```python
    // ... existing imports ...
    from huleedu_service_libs.redis_client import RedisClient
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    // ... existing ApiGatewayProvider class ...

        @provide(scope=Scope.APP)
        async def provide_redis_client(self) -> AtomicRedisClientProtocol:
            client = RedisClient(client_id=settings.SERVICE_NAME, redis_url=settings.REDIS_URL)
            await client.start()
            return client
    ```

2. **Implement the Enhanced WebSocket Endpoint Router**: This handler manages the connection lifecycle, authentication, and message forwarding with support for enhanced event types.

    **File**: `services/api_gateway_service/routers/websocket_routes.py`

    ```python
    import asyncio
    import json
    from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
    from dishka.integrations.fastapi import FromDishka
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol
    from huleedu_service_libs.logging_utils import create_service_logger
    from .. import auth

    router = APIRouter()
    logger = create_service_logger("api_gateway.websocket")

    # Define a separate auth function for WebSockets to handle token from query param
    async def get_user_id_from_ws(token: str | None = Query(None)) -> str:
        if token is None:
             raise WebSocketDisconnect(code=1008, reason="Missing token")
        return await auth.get_current_user_id(token)

    @router.websocket("/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        user_id: str = Depends(get_user_id_from_ws), # Authenticate via query parameter
        redis_client: FromDishka[AtomicRedisClientProtocol],
    ):
        await websocket.accept()
        user_channel = f"ws:{user_id}"
        
        logger.info(f"WebSocket connection established for user: {user_id}")

        async def redis_listener(ws: WebSocket, ps_client):
            async for message in ps_client.listen():
                if message and message["type"] == "message":
                    try:
                        # Parse message to validate structure and add client-side filtering
                        event_data = json.loads(message["data"])
                        event_type = event_data.get("event")
                        
                        # Enhanced event routing and validation
                        if event_type in [
                            "batch_phase_concluded", 
                            "essay_status_updated",
                            "batch_file_added",
                            "batch_file_removed", 
                            "batch_locked_for_processing",
                            "student_parsing_completed",
                            "essay_student_association_updated",
                            "class_created",
                            "class_updated", 
                            "student_created",
                            "student_updated"
                        ]:
                            await ws.send_text(message["data"])
                            logger.debug(f"Sent {event_type} event to user {user_id}")
                        else:
                            logger.warning(f"Unknown event type received: {event_type}")
                            
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in Redis message: {message['data']}")
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")

        async def pinger(ws: WebSocket):
            while True:
                try:
                    await asyncio.sleep(15)
                    await ws.send_json({"event": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
                except (WebSocketDisconnect, asyncio.CancelledError):
                    break

        listener_task = None
        pinger_task = None
        try:
            async with redis_client.subscribe(user_channel) as pubsub:
                listener_task = asyncio.create_task(redis_listener(websocket, pubsub))
                pinger_task = asyncio.create_task(pinger(websocket))

                done, pending = await asyncio.wait(
                    [listener_task, pinger_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user: {user_id}")
        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")
        finally:
            if listener_task and not listener_task.done():
                listener_task.cancel()
            if pinger_task and not pinger_task.done():
                pinger_task.cancel()
            logger.info(f"WebSocket cleanup completed for user: {user_id}")
    ```

3. **Update `main.py` to Register the WebSocket Router**:

    **File**: `services/api_gateway_service/main.py`

    ```python
    // ... existing imports ...
    from .routers import pipeline_routes, status_routes, websocket_routes // Add websocket_routes

    // ... app setup ...

    // Register Routers
    app.include_router(pipeline_routes.router, prefix="/v1", tags=["Pipelines"])
    app.include_router(status_routes.router, prefix="/v1", tags=["Status"]) // Add this line
    app.include_router(websocket_routes.router, tags=["Real-time"]) // Add this line
    ```

**Enhanced Event Types Supported**:

The WebSocket implementation now supports these additional event types for the enhanced features:

- **File Management Events**:
  - `batch_file_added`: When files are added to a batch (before spellcheck)
  - `batch_file_removed`: When files are removed from a batch (before spellcheck)
  - `batch_locked_for_processing`: When spellcheck starts and batch becomes locked

- **Student Association Events**:
  - `student_parsing_completed`: When automatic student parsing finishes
  - `essay_student_association_updated`: When manual student-essay associations are made

- **Class Management Events**:
  - `class_created`: When new classes are created
  - `class_updated`: When class information is modified
  - `student_created`: When new students are added
  - `student_updated`: When student information is modified

**Done When**:

- ✅ A client can establish an authenticated WebSocket connection via `/ws?token=<jwt>`.
- ✅ The gateway correctly subscribes to the user-specific Redis channel (e.g., `ws:user_123`).
- ✅ The connection is kept alive via a server-side heartbeat and gracefully closed on disconnect.
- ✅ Heartbeat messages use `{ "event": "ping" }` so all WebSocket payloads share the same `event` field.
- ✅ Enhanced event types for file management, student associations, and class management are properly routed.
- ✅ Event validation prevents malformed messages from reaching clients.
- ✅ Comprehensive logging tracks WebSocket lifecycle and event routing.

### Checkpoint 3.3: Modify Backend Services to Publish Enhanced Updates

**Objective**: Complete the real-time feedback loop by making BOS, ELS, File Service, and the new Class Management Service publish state changes to the Redis backplane.

**Affected Files**:

- `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`
- `services/batch_orchestrator_service/di.py`
- `services/essay_lifecycle_service/implementations/service_result_handler_impl.py`
- `services/essay_lifecycle_service/di.py`
- `services/file_service/implementations/event_publisher_impl.py` (enhanced)
- `services/class_management_service/implementations/event_publisher_impl.py` (new)

**Implementation Steps**:

1. **Inject Redis Client into BOS**: Update the Dishka provider and the `DefaultPipelinePhaseCoordinator` to accept the Redis client.

    **File**: `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`

    ```python
    // ...
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    class DefaultPipelinePhaseCoordinator:
        def __init__(
            self,
            batch_repo: BatchRepositoryProtocol,
            phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
            redis_client: AtomicRedisClientProtocol, // Add this
        ) -> None:
            self.batch_repo = batch_repo
            self.phase_initiators_map = phase_initiators_map
            self.redis_client = redis_client // Add this
    // ...
    ```

    Ensure the `redis_client` is added to the provider signature in `services/batch_orchestrator_service/di.py`.

2. **Add Enhanced Redis Publish Logic to BOS**: In the `handle_phase_concluded` method, after updating the database, publish the status change with enhanced event types.

    **File**: `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`

    ```python
    // ... inside handle_phase_concluded method ...
        await self.update_phase_status(
            batch_id,
            completed_phase,
            updated_status,
            datetime.now(timezone.utc).isoformat(),
        )

        # Enhanced Redis publishing with batch lock detection
        batch_context = await self.batch_repo.get_batch_context(batch_id)
        user_id = None
        if batch_context and batch_context.processing_metadata:
            user_id = batch_context.processing_metadata.get("user_id")

        if user_id:
            # Standard phase conclusion event
            redis_message = {
                "event": "batch_phase_concluded",
                "batch_id": batch_id,
                "phase": completed_phase,
                "status": updated_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))
            
            # Special handling for spellcheck phase - marks batch as locked
            if completed_phase == "SPELLCHECK" and updated_status == "COMPLETED":
                lock_message = {
                    "event": "batch_locked_for_processing",
                    "batch_id": batch_id,
                    "locked_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "Spellcheck completed - no further file modifications allowed"
                }
                await self.redis_client.publish(f"ws:{user_id}", json.dumps(lock_message))
                
        else:
            self.logger.warning(f"User ID not found in batch context for batch '{batch_id}'. Skipping real-time update.")
    // ...
    ```

3. **Enhanced File Service Event Publishing**: Update File Service to publish file management events.

    **File**: `services/file_service/implementations/event_publisher_impl.py`

    ```python
    async def publish_file_added_event(
        self, 
        batch_id: str, 
        essay_id: str, 
        filename: str, 
        user_id: str
    ) -> None:
        """Publish real-time update when file is added to batch."""
        redis_message = {
            "event": "batch_file_added",
            "batch_id": batch_id,
            "essay_id": essay_id,
            "filename": filename,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))

    async def publish_file_removed_event(
        self, 
        batch_id: str, 
        essay_id: str, 
        filename: str, 
        user_id: str
    ) -> None:
        """Publish real-time update when file is removed from batch."""
        redis_message = {
            "event": "batch_file_removed",
            "batch_id": batch_id,
            "essay_id": essay_id,
            "filename": filename,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))

    async def publish_student_parsing_completed_event(
        self,
        batch_id: str,
        parsing_results: list[StudentParsingResult],
        user_id: str
    ) -> None:
        """Publish real-time update when student parsing completes."""
        redis_message = {
            "event": "student_parsing_completed",
            "batch_id": batch_id,
            "parsed_count": len([r for r in parsing_results if r.student_name]),
            "total_count": len(parsing_results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))
    ```

4. **Class Management Service Event Publishing**: Create event publisher for class and student management.

    **File**: `services/class_management_service/implementations/event_publisher_impl.py`

    ```python
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol
    import json
    from datetime import datetime, timezone

    class ClassManagementEventPublisher:
        def __init__(self, redis_client: AtomicRedisClientProtocol):
            self.redis_client = redis_client

        async def publish_class_created_event(
            self, 
            class_id: str, 
            class_designation: str, 
            user_id: str
        ) -> None:
            """Publish real-time update when class is created."""
            redis_message = {
                "event": "class_created",
                "class_id": class_id,
                "class_designation": class_designation,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))

        async def publish_student_created_event(
            self, 
            student_id: str, 
            student_name: str, 
            student_email: str, 
            user_id: str
        ) -> None:
            """Publish real-time update when student is created."""
            redis_message = {
                "event": "student_created",
                "student_id": student_id,
                "student_name": student_name,
                "student_email": student_email,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))

        async def publish_essay_student_association_event(
            self,
            batch_id: str,
            essay_id: str,
            student_id: str,
            association_method: str,
            user_id: str
        ) -> None:
            """Publish real-time update when essay-student association is made."""
            redis_message = {
                "event": "essay_student_association_updated",
                "batch_id": batch_id,
                "essay_id": essay_id,
                "student_id": student_id,
                "association_method": association_method,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.publish(f"ws:{user_id}", json.dumps(redis_message))
    ```

5. **Repeat Enhanced Logic for ELS**: Perform the same dependency injection and logic addition for the `DefaultServiceResultHandler` in the `essay_lifecycle_service`, adding essay status update events.

**Done When**:

- ✅ When BOS or ELS processes an event that changes the state of a batch or essay, a corresponding JSON message is published to the correct user-specific Redis channel.
- ✅ File Service publishes real-time updates for file additions, removals, and student parsing completion.
- ✅ Class Management Service publishes updates for class/student creation and essay-student associations.
- ✅ Batch locking events are published when spellcheck begins.
- ✅ End-to-end tests (see below) confirm that enhanced client actions trigger appropriate WebSocket messages.

### Checkpoint 3.4: Final Testing and Contract Generation

**Objective**: Verify the entire workflow and formalize the client-backend contract.

**Affected Files**:

- `tests/functional/test_e2e_client_interface.py` (new)
- `pyproject.toml` (modification in root)

**Implementation Steps**:

1. **Write End-to-End Test**: Create a new functional test that:
    a. Mocks user authentication to generate a valid JWT.
    b. Creates a test batch via the API gateway.
    c. Establishes an authenticated WebSocket connection.
    d. Triggers backend processing by publishing a `BatchEssaysReady` event to Kafka (simulating the ELS).
    e. Listens on the WebSocket and asserts that the expected `batch_phase_concluded` message is received from BOS.

2. **Automate Frontend Contract Generation**: Add a script to the root `pyproject.toml` to generate TypeScript types from the gateway's OpenAPI schema. Use `app.openapi()` directly so the gateway does not need to be running.

    **File**: `pyproject.toml`

    ```toml
    [tool.pdm.scripts]
    # ... existing scripts ...
    generate-frontend-types = "python services/api_gateway_service/scripts/dump_openapi.py > openapi.json && openapi-typescript openapi.json -o frontend/src/api-client/schema.ts"
    ```

    This script will be added as a mandatory CI check.

**Done When**:

- ✅ The new E2E test passes, proving the entire loop from HTTP command to WebSocket update is functional.
- ✅ The `pdm run generate-frontend-types` command successfully generates a `schema.ts` file without starting the gateway service.
