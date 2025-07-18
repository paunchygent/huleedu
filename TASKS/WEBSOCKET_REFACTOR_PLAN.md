# WebSocket Service Refactoring: Architectural Validation and Implementation Plan

## Executive Summary

This report validates the architectural mandate to refactor WebSocket handling into a dedicated microservice. The current implementation, co-located within the `api_gateway_service`, presents a significant scalability and resilience risk. The `api_gateway_service` is designed for stateless request-response cycles, and forcing it to manage stateful, long-lived WebSocket connections creates an architectural conflict that compromises the entire system's stability.

The evidence confirms that a dedicated `websocket_service` is the superior architecture. This refactoring will improve fault isolation, enable independent scaling, and align with our microservices philosophy. The following implementation plan outlines a clean, no-fallback refactoring to be executed as a single, atomic operation.

**Final Recommendation:** GO.

---

## 1. Evidence from Investigation

### Workstream 1: Assess the Current Implementation

* **WebSocket Logic Location**: The WebSocket connection logic is located in `services/api_gateway_service/routers/websocket_routes.py`.

* **Host Service**: `api_gateway_service`.

* **Host Service Responsibilities**:
  * **API Routes**: The service acts as a reverse proxy, handling authentication (JWT), rate-limiting, and routing for:
    * Batch processing commands (`/v1/batches/...`)
    * File uploads (`/v1/files/batch`)
    * Class management (`/v1/classes/...`)
  * **Dependencies**: It communicates with `file_service`, `class_management_service`, and uses Kafka for command publishing and Redis for rate-limiting and WebSocket message passing.

* **Architectural Conflict**: The `api_gateway_service` is fundamentally a **stateless request-response proxy**. Its core purpose is to efficiently process and route short-lived HTTP requests. Stateful WebSocket connections are a stark contrast. They are long-lived, consume memory per-connection, and require a different scaling strategy. Forcing a stateless gateway to manage stateful connections violates the Single Responsibility Principle and creates a direct conflict in resource management and scaling needs.

### Workstream 2: Evaluate Scalability & Resilience

* **High-Congestion Scenario (100,000 Concurrent Connections)**:
  * **Service Under Load**: The `api_gateway_service` would bear the full load.
  * **Resource Inefficiency**: To support 100,000 WebSocket connections, we would need to scale out the *entire* `api_gateway_service`. This means unnecessarily replicating all its components—the routing logic, the authentication handlers, the multiple HTTP proxy clients—just to handle more WebSocket connections. This is highly inefficient. A dedicated service would scale its lean connection-handling logic independently.

* **Failure Scenario (DoS Attack on WebSockets)**:
  * **Blast Radius**: A DoS attack exhausting the WebSocket connection pool would cripple the `api_gateway_service`. Because it is the single entry point for all client traffic, its failure would bring down **all other critical functionalities**. The React frontend would be unable to manage batches, upload files, or interact with classes. The entire platform would become unavailable.

* **Fault Isolation**:
  * **Answer**: No.
  * **Evidence**: The co-location of critical, stateless API gateway logic with stateful WebSocket handling means there is zero fault isolation. A failure in the WebSocket system directly translates to a failure of the entire API gateway, as demonstrated in the DoS scenario.

### Workstream 3: Deconstruct the Refactoring Proposal

* **New `websocket_service` Definition**:
  * **Framework**: A lightweight Python framework like Quart or FastAPI.
  * **Core Logic**:
    * A single WebSocket endpoint (e.g., `/ws`).
    * Connection management logic to handle the lifecycle of each WebSocket.
    * A Redis Pub/Sub listener to subscribe to user-specific notification channels.
    * A message forwarding task to push messages from Redis to the client.
  * **Dependencies**: `redis`, `pydantic`, and our `common_core` library. It will **not** have dependencies on other services' HTTP clients.

* **Authentication**:
  * **Method**: JWT-based authentication, consistent with the existing system.
  * **Implementation**: The client will pass the JWT as a query parameter (e.g., `ws://huleedu.io/ws?token=...`). The `websocket_service` will use a shared authentication utility (from `huleedu_service_libs`) to decode and validate the token upon connection. If validation fails, the connection is immediately rejected with a `1008 POLICY_VIOLATION` code.

* **Configuration Changes**:
  * **`docker-compose.services.yml`**: A new service entry for `websocket_service` will be added.
  * **Environment Variables**:
    * `WEBSOCKET_SERVICE_PORT`
    * `WEBSOCKET_REDIS_URL`
    * `JWT_SECRET_KEY`
  * **Client-Side Config**: The frontend application's WebSocket connection URL will be updated to point to the new service's address and port.
  * **API Gateway**: The old `/ws/...` route will be completely removed.

* **Inter-Service Communication**:
  * **Backplane**: Redis Pub/Sub is confirmed as the correct and sufficient backplane. Backend services will continue to publish user-specific notifications to Redis channels (e.g., `ws:{user_id}`). The new `websocket_service` will be the sole subscriber to these channels, forwarding messages to the appropriate clients. This decouples the `websocket_service` from the business logic of other services.

---

## 2. Definitive Implementation Plan

This plan adheres to the **No Legacy Fallback** constraint. The refactoring will be performed as a single, atomic operation.

1. **Create New Service (`websocket_service`)**:
    * Initialize a new service directory: `services/websocket_service`.
    * Create a minimal FastAPI/Quart application.
    * Implement the WebSocket endpoint (`/ws`) with JWT authentication via query parameters.
    * Implement the Redis Pub/Sub listener and message forwarding logic.
    * Add comprehensive tests for connection handling, authentication, and message forwarding.

2. **Update Infrastructure and Configuration**:
    * Add the `websocket_service` to `docker-compose.services.yml`.
    * Define and document the necessary environment variables.

3. **Remove Legacy Implementation**:
    * **Delete** the file `services/api_gateway_service/routers/websocket_routes.py`.
    * Remove the WebSocket router import and registration from `services/api_gateway_service/app/main.py`.
    * Delete all WebSocket-related tests from `services/api_gateway_service/tests/`.
    * Remove any WebSocket-specific configurations from the `api_gateway_service`.

4. **Update Client Application**:
    * Modify the frontend's configuration to point the WebSocket connection to the new `websocket_service` endpoint.

5. **Testing and Validation**:
    * Run all tests for the new `websocket_service`.
    * Run all tests for the `api_gateway_service` to ensure no regressions were introduced.
    * Perform an end-to-end test to verify that a backend event is successfully published to Redis and received by a client connected to the new `websocket_service`.
