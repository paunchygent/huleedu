---
id: ARCH-001
title: "Refactor WebSocket Handling to a Dedicated Microservice"
author: "CTO"
status: "Ready for Development"
created_date: "2025-07-18"
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
