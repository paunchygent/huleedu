# API Gateway WebSocket Service

## 1\. Overview

The API Gateway provides real-time, server-pushed notifications to authenticated clients via a WebSocket interface. It acts as a bridge, subscribing to backend events on **Redis Pub/Sub** channels and securely forwarding them to the appropriate client.

## 2\. Connection Endpoint

- **URL**: `ws://<host>/ws/v1/status/{client_id}`
- **File**: `routers/websocket_routes.py`
- **`client_id`**: The unique identifier for the client connection. This **must** match the `user_id` of the authenticated user.

## 3\. Authentication

WebSocket connections are authenticated using the same JWT mechanism as the REST API, but the token is passed as a query parameter.

- **Mechanism**: The `websocket_status_endpoint` depends on `auth.get_current_user_id`, which is configured to extract the token from the `token` query parameter for WebSocket routes.
- **Example Connection URL**: `ws://localhost:8080/ws/v1/status/user-abc-123?token=eyJhbGciOi...`
- **Validation**: The service validates that the `user_id` from the decoded JWT matches the `{client_id}` provided in the URL path. If they do not match, the connection is closed with a `1008_POLICY_VIOLATION` code.

```python
# File: services/api_gateway_service/routers/websocket_routes.py

# ...
user_id: str = Depends(auth.get_current_user_id),
# ...
if client_id != user_id:
    # ...
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return
```

## 4\. Architecture: Redis Pub/Sub Bridge

The WebSocket endpoint does not consume from Kafka directly. Instead, it subscribes to a user-specific Redis channel, providing a scalable and decoupled notification system.

1. **Subscription**: Upon a successful, authenticated connection, the service subscribes to a unique Redis channel for that user. The channel name is standardized as `ws:{user_id}`. This is handled by the `redis_client.subscribe()` method.
2. **Concurrent Listener**: A dedicated `redis_listener` task is created using `asyncio.create_task` to listen for messages on the subscribed channel without blocking the main WebSocket connection loop.
3. **Message Forwarding**: When a message is received from Redis, the `redis_listener` decodes it and sends it as a text payload over the WebSocket to the client (`await websocket.send_text(data)`).
4. **Backend Publishing**: Internal services (like `class_management_service`) are responsible for publishing notifications to the appropriate user's Redis channel when a relevant event occurs. They use the `redis_client.publish_user_notification()` helper for this purpose.
5. **Disconnection Handling**: The main `try...finally` block listens for a `WebSocketDisconnect` exception. When the client disconnects, the `listener_task` is cancelled, ensuring the Redis subscription is properly closed and resources are released.
