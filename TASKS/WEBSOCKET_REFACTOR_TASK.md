---
id: ARCH-001
title: "Refactor WebSocket Handling to a Dedicated Microservice"
author: "CTO"
status: "Refactor Complete - Improvements Needed"
created_date: "2025-07-18"
updated_date: "2025-07-19"
---

## 1. Objective

This document outlines the phased implementation plan to refactor WebSocket handling from the `api_gateway_service` into a new, dedicated `websocket_service`. This refactoring is a mandatory architectural improvement to enhance scalability, resilience, and maintainability, adhering strictly to the "No Legacy Fallback" constraint.

## 2. Architectural Drivers

- **Single Responsibility Principle**: The `api_gateway_service` is a stateless request proxy. Managing stateful WebSocket connections violates this principle.
- **Scalability**: A dedicated service allows for independent scaling of WebSocket connection handling without scaling the entire API Gateway.
- **Fault Isolation**: Isolating WebSocket handling prevents connection-related issues (e.g., DoS attacks, resource exhaustion) from impacting the entire API Gateway and its critical functions.
- **Resource Management**: A lightweight `websocket_service` can be optimized for managing a large number of concurrent, long-lived connections with a smaller resource footprint.

## 3. Phased Implementation Plan

This refactoring will be executed in a single, atomic operation on the codebase, but is broken down into logical phases for clarity.

### Phase 1: Create the New `websocket_service`

This phase focuses on building the new, standalone service according to our architectural standards.

**Task 1.1: Initialize Service Scaffolding**

- Create a new directory: `services/websocket_service`.
- Initialize a new PDM project with a `pyproject.toml` file.
  - Dependencies: `fastapi`, `uvicorn`, `dishka[fastapi]`, `huleedu-common-core`, `huleedu-service-libs`.
- Create the basic directory structure: `app/`, `routers/`, `tests/`, `config.py`, `di.py`, `protocols.py`.

**Task 1.2: Implement Core WebSocket Logic**

- Create a new FastAPI application in `app/main.py`.
- In `routers/websocket_router.py`, create a single WebSocket endpoint: `@router.websocket("/ws")`.
- Implement JWT authentication for the WebSocket endpoint.
  - The JWT token will be passed as a query parameter (`?token=...`).
  - Use the existing `auth.get_current_user_id` logic, adapted for WebSockets.
- Implement the Redis Pub/Sub listener logic.
  - The service will subscribe to user-specific channels (e.g., `ws:{user_id}`).
  - Use the `RedisPubSub` client from `huleedu_service_libs`.
- Implement the message forwarding logic to push messages from Redis to the connected client.

**Task 1.3: Implement Dependency Injection**

- In `di.py`, create a Dishka `Provider` for the service.
- Provide the `AtomicRedisClientProtocol` from `huleedu_service_libs`.
- Ensure all dependencies are injected using the `@inject` decorator.

**Task 1.4: Add Configuration and Dockerization**

- In `config.py`, define the necessary settings using `pydantic-settings`.
  - `WEBSOCKET_SERVICE_PORT`, `REDIS_URL`, `JWT_SECRET_KEY`.
- Create a `Dockerfile` for the service, ensuring `PYTHONPATH=/app` is set.
- Add a new service entry to `docker-compose.services.yml` for `websocket_service`.

**Task 1.5: Implement Testing**

- Create unit and integration tests in the `tests/` directory.
- **MUST** mock protocol interfaces (`AtomicRedisClientProtocol`) for unit tests.
- **MUST** include tests for:
  - Successful connection and authentication.
  - Unauthorized connection attempts.
  - Message forwarding from Redis.
  - Graceful disconnection and resource cleanup.

### Phase 2: Remove Legacy Implementation

This phase ensures the complete removal of the old WebSocket logic from the `api_gateway_service`.

**Task 2.1: Delete WebSocket Code**

- **Delete** the file `services/api_gateway_service/routers/websocket_routes.py`.
- In `services/api_gateway_service/app/main.py`:
  - Remove the import for `websocket_routes`.
  - Remove the line `app.include_router(websocket_routes.router, ...)`.
- **Delete** the test file `services/api_gateway_service/tests/test_websocket_routes.py`.

**Task 2.2: Clean Up Dependencies**

- Review `services/api_gateway_service/pyproject.toml` and remove any dependencies that were solely for WebSocket handling, if any.

### Phase 3: Update Documentation and Signal Client-Side Changes

This phase ensures our documentation is aligned with the new architecture and provides clear guidance for the frontend team.

**Task 3.1: Document Client-Side Contract**

- The `websocket_service` exposes a new endpoint. This constitutes a change in the client-facing contract. A note must be added to the project's central API documentation or a designated frontend communication channel, specifying:
  - The new WebSocket endpoint URL (e.g., `ws://<host>:<port>/ws`).
  - The requirement for the JWT to be passed as a query parameter (`?token=...`).
- This task is about *documenting* the change for the frontend team, not implementing it in the frontend codebase.

**Task 3.2: Update Service and Architectural Documentation**

- Update the `README.md` for the `api_gateway_service` to remove any mention of WebSocket handling.
- Create a new `README.md` for the `websocket_service` following the standards in rule `090-documentation-standards.mdc`.
- Update any relevant architectural diagrams or documentation to reflect the new service.

## 4. Verification and Validation

- All existing tests for the `api_gateway_service` **MUST** pass after the refactoring.
- All new tests for the `websocket_service` **MUST** pass.
- An end-to-end test **MUST** be performed to verify the complete notification flow:
  1. A backend service publishes an event.
  2. The event triggers a notification to a Redis channel.
  3. The `websocket_service` receives the message from Redis.
  4. The `websocket_service` forwards the message to a connected client.

## 5. Final Recommendation

This refactoring is a critical step in maturing our architecture. The "GO" decision is confirmed. Proceed with the implementation as outlined above.

## 6. Implementation Status (Updated: 2025-07-18)

### Phase 1: Create the New `websocket_service` ✅ COMPLETE

**Completed Tasks:**
- ✅ Task 1.1: Service scaffolding initialized with proper directory structure
- ✅ Task 1.2: Core WebSocket logic implemented with JWT auth and Redis Pub/Sub
- ✅ Task 1.3: Dependency injection configured with Dishka providers
- ✅ Task 1.4: Configuration and Docker integration complete
- ✅ Task 1.5: Testing suite implemented with unit and integration tests

**Evidence of Completion:**
- Service directory: `services/websocket_service/` fully populated
- FastAPI app running on port 8004
- WebSocket endpoint: `/ws` with JWT query parameter authentication
- Redis integration using `AtomicRedisClientProtocol`
- Docker service entry in `docker-compose.services.yml`
- Test files created in `tests/` directory

### Phase 2: Remove Legacy Implementation ✅ COMPLETE

**Completed Tasks:**
- ✅ Task 2.1: Delete WebSocket code
  - Removed `services/api_gateway_service/routers/websocket_routes.py`
  - Removed imports and registration from `main.py`
  - Removed test file `services/api_gateway_service/tests/test_websocket_routes.py`
  - Removed `services/api_gateway_service/WEBSOCKET_README.md`
- ✅ Task 2.2: Dependencies cleaned up

**Evidence of Completion:**
- All WebSocket-related code removed from API Gateway
- API Gateway tests passing without WebSocket functionality
- Service successfully running without WebSocket routes

### Phase 3: Update Documentation ✅ COMPLETE

**Completed Tasks:**
- ✅ Task 3.1: Documented client-side contract changes
  - New endpoint: `ws://websocket-service:8004/ws?token={jwt}`
  - Old endpoint removed: `ws://api-gateway:8080/ws/v1/status/{client_id}`
  - Authentication method change: header → query parameter
- ✅ Task 3.2: Service documentation updated
  - Removed WebSocket references from API Gateway README
  - WebSocket service README created and reviewed

### Phase 4: Verification and Validation ✅ COMPLETE

**Completed Tasks:**
- ✅ All API Gateway tests passing post-removal
- ✅ All WebSocket service tests passing
- ✅ End-to-end notification flow verified
- ✅ Basic functionality validated

**Note:** While functional verification is complete, performance optimization and comprehensive testing coverage improvements are tracked in the post-refactor improvements section.

## 7. Technical Decisions Made

1. **Authentication**: JWT passed as query parameter (`?token=xxx`) due to WebSocket upgrade limitations
2. **Framework**: FastAPI chosen for consistency with API Gateway
3. **Message Format**: Maintained existing format for backward compatibility
4. **Channel Pattern**: Redis channels use `ws:{user_id}` format
5. **Error Codes**: Using standard WebSocket close codes (1008 for policy violation)

## 8. Known Issues and Considerations

1. **Frontend Impact**: Client applications must update WebSocket connection URL and auth method
2. **Monitoring**: Prometheus metrics need to be validated in new service
3. **Scaling**: Horizontal scaling strategy needs testing with Redis backplane
4. **Message Ordering**: Redis Pub/Sub doesn't guarantee order - acceptable for notifications

## 9. Next Steps (Original - All Complete)

1. ✅ Complete Phase 2 by removing all legacy code from API Gateway
2. ✅ Create frontend migration guide with clear examples (documented in service README)
3. ✅ Coordinate with frontend team for client updates (contract documented)
4. ⏸️ Schedule load testing for new service (moved to improvements)
5. ✅ Plan gradual rollout strategy if needed (single cutover completed)

## 10. Post-Refactor Improvements Identified

During the implementation and verification phases, several areas for improvement were identified:

### 10.1 Test Coverage Issues
- **Current State**: Test coverage at 75%
- **Target**: >90% coverage following project standards
- **Gap Areas**:
  - Edge cases in connection handling
  - Error scenarios and recovery paths
  - Integration tests with multiple concurrent connections
  - Authentication failure scenarios

### 10.2 Error Handling Improvements
- **Current State**: Basic error handling with standard WebSocket close codes
- **Required**: Implementation of HuleEduError pattern
- **Specific Needs**:
  - Structured error responses using `error_detail` field
  - Integration with observability stack
  - Proper error categorization and logging

### 10.3 Observability Enhancements
- **Missing**: OpenTelemetry spans for WebSocket operations
- **Required**: Full tracing implementation including:
  - Connection lifecycle spans
  - Message processing traces
  - Redis operation spans
  - Error tracking integration

### 10.4 Service Enhancements
- **Connection Management**: Implement heartbeat/ping-pong mechanism
- **Graceful Shutdown**: Enhance shutdown sequence for active connections
- **Message Buffering**: Add buffering for high-throughput scenarios
- **Metrics**: Expand Prometheus metrics for better monitoring

### 10.5 Performance Optimizations
- **Connection Pooling**: Optimize Redis connection management
- **Message Batching**: Implement batching for multiple messages
- **Resource Limits**: Add configurable connection limits
- **Load Testing**: Comprehensive performance validation needed

## 11. Next Steps - Post-Refactor

The WebSocket refactor is functionally complete, but requires improvements to meet production standards:

### 11.1 Immediate Priorities (P0)
1. **Test Coverage**: Increase to >90% following `/TASKS/WEBSOCKET_POST_REFACTOR_IMPROVEMENTS.md`
2. **Error Handling**: Implement HuleEduError pattern throughout the service
3. **Observability**: Add OpenTelemetry spans for critical operations

### 11.2 Short-term Improvements (P1)
1. **Connection Management**: Implement heartbeat mechanism
2. **Graceful Shutdown**: Enhance shutdown handling
3. **Metrics**: Expand Prometheus coverage

### 11.3 Long-term Enhancements (P2)
1. **Performance**: Conduct load testing and optimization
2. **Message Buffering**: Implement for high-throughput scenarios
3. **Advanced Features**: Consider message history, replay capabilities

### 11.4 Implementation Guidance
- **Detailed Plan**: See `/TASKS/WEBSOCKET_POST_REFACTOR_IMPROVEMENTS.md`
- **Session Prompt**: Use `/TASKS/WEBSOCKET_IMPROVEMENTS_SESSION_PROMPT.md` for next session
- **Priority Order**: Focus on P0 items first to meet project standards

### 11.5 Success Criteria
- Test coverage >90%
- All errors using HuleEduError pattern
- Full OpenTelemetry integration
- Passing all integration tests
- Performance benchmarks established
