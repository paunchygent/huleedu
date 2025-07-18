# WebSocket Service

A dedicated microservice for handling WebSocket connections and real-time notifications in the HuleEdu platform.

## Overview

The WebSocket Service provides real-time communication capabilities by:

- Managing WebSocket connections with JWT authentication
- Subscribing to user-specific Redis channels
- Forwarding messages from backend services to connected clients
- Supporting multiple concurrent connections per user

## Architecture

### Key Components

1. **WebSocket Manager**: Tracks active connections per user with configurable limits
2. **JWT Validator**: Validates tokens passed as query parameters
3. **Message Listener**: Subscribes to Redis pub/sub channels and forwards messages
4. **Metrics Collector**: Prometheus metrics for monitoring

### Design Decisions

- **Extracted from API Gateway**: Follows Single Responsibility Principle
- **FastAPI Framework**: Excellent WebSocket support via Starlette
- **Redis Pub/Sub**: Decouples message producers from WebSocket connections
- **Query Parameter Auth**: Pragmatic solution for WebSocket authentication

## API Endpoints

### WebSocket Endpoint

- **URL**: `ws://localhost:8080/ws?token=<JWT_TOKEN>`
- **Authentication**: JWT token as query parameter
- **Protocol**: Text-based JSON messages

### Health Endpoints

- `GET /healthz` - Basic health check
- `GET /healthz/redis` - Redis connectivity check
- `GET /healthz/websocket` - WebSocket manager status
- `GET /metrics` - Prometheus metrics

## Configuration

Key environment variables:

```bash
# Service Configuration
WEBSOCKET_PORT=8080
WEBSOCKET_MAX_CONNECTIONS_PER_USER=5
WEBSOCKET_IDLE_TIMEOUT=300

# Redis Configuration
REDIS_URL=redis://redis:6379

# JWT Configuration
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256

# CORS Configuration
CORS_ORIGINS=["http://localhost:3000"]
```

## Development

### Running Locally

```bash
# Install dependencies
pdm install

# Run the service
pdm run dev
```

### Running Tests

```bash
# Run all tests
pdm run test

# Run with coverage
pdm run test-cov
```

### Docker Build

```bash
docker build -t websocket-service .
docker run -p 8080:8080 websocket-service
```

## Message Flow

1. Backend service publishes notification to Redis channel `ws:{user_id}`
2. WebSocket service receives message from Redis subscription
3. Service forwards message to all active WebSocket connections for that user
4. Client receives real-time notification

## Metrics

The service exposes Prometheus metrics including:

- `websocket_connections_total` - Total connections by status
- `websocket_active_connections` - Currently active connections per user
- `websocket_messages_sent_total` - Messages sent to clients
- `websocket_connection_duration_seconds` - Connection duration histogram

## Security

- JWT authentication required for all connections
- Token expiry validation
- Connection limits per user to prevent resource exhaustion
- Automatic cleanup of stale connections

## Integration

The service integrates with:

- **Redis**: For pub/sub message delivery
- **Backend Services**: Via Redis channels for notifications
- **Frontend**: WebSocket clients for real-time updates
