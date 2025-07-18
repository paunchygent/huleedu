# WebSocket Service Implementation Plan

## Executive Summary

This document provides a comprehensive implementation plan for the new `websocket_service` following HuleEdu's established architectural patterns. The service will be a dedicated FastAPI-based microservice handling WebSocket connections with JWT authentication and Redis Pub/Sub integration.

---

## Phase 1: Service Scaffolding

### 1.1 Directory Structure

```
services/websocket_service/
├── main.py                      # FastAPI app creation and setup
├── startup_setup.py             # DI container, middleware, metrics
├── routers/
│   ├── __init__.py
│   ├── health_routes.py         # Health and metrics endpoints
│   └── websocket_routes.py      # WebSocket endpoint with auth
├── models/
│   ├── __init__.py
│   ├── requests.py              # Connection request models
│   └── responses.py             # WebSocket message models
├── protocols.py                 # Behavioral contracts
├── implementations/
│   ├── __init__.py
│   ├── connection_manager.py    # WebSocket connection lifecycle
│   ├── redis_subscriber.py      # Redis Pub/Sub implementation
│   └── auth_validator.py        # JWT validation logic
├── di.py                        # Dishka providers
├── config.py                    # Pydantic settings
├── pyproject.toml               # PDM configuration
├── Dockerfile                   # Service container
├── README.md                    # Service documentation
└── tests/
    ├── __init__.py
    ├── conftest.py              # Test fixtures and DI setup
    ├── unit/
    │   ├── test_connection_manager.py
    │   ├── test_redis_subscriber.py
    │   └── test_auth_validator.py
    ├── integration/
    │   ├── test_websocket_auth.py
    │   └── test_redis_pubsub.py
    └── contract/
        └── test_message_formats.py
```

### 1.2 PDM Configuration (pyproject.toml)

```toml
[project]
name = "websocket-service"
version = "0.1.0"
description = "WebSocket Service for HuleEdu Platform"
authors = [
    { name = "HuleEdu Team", email = "team@huleedu.io" }
]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.1,<1.0.0",
    "websockets>=12.0",
    "uvicorn[standard]>=0.24.0",
    "redis>=5.0.1",
    "aioredis>=2.0.1",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "PyJWT>=2.8.0",
    "dishka>=1.2.0",
    "prometheus-client>=0.19.0",
    "python-dotenv>=1.0.0",
    "common-core @ file:///${PROJECT_ROOT}/libs/common_core",
    "huleedu-service-libs @ file:///${PROJECT_ROOT}/libs/huleedu_service_libs",
]

[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"

[tool.pdm.scripts]
dev = "uvicorn main:app --reload --host 0.0.0.0 --port 8004"
start = "uvicorn main:app --host 0.0.0.0 --port 8004"
test = "pytest"
format = "ruff format ."
lint = "ruff check ."
typecheck = "mypy ."
```

### 1.3 Protocol Definitions (protocols.py)

```python
"""WebSocket service behavioral contracts."""
from __future__ import annotations

from typing import Protocol, AsyncIterator, Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class ConnectionManagerProtocol(Protocol):
    """Manages WebSocket connections and message routing."""
    
    async def connect(self, websocket: Any, user_id: str) -> None:
        """Register a new WebSocket connection."""
        ...
    
    async def disconnect(self, user_id: str) -> None:
        """Remove a WebSocket connection."""
        ...
    
    async def send_personal_message(self, message: str, user_id: str) -> None:
        """Send a message to a specific user."""
        ...
    
    async def is_user_connected(self, user_id: str) -> bool:
        """Check if a user has an active connection."""
        ...


class RedisSubscriberProtocol(Protocol):
    """Handles Redis Pub/Sub subscriptions."""
    
    async def start(self) -> None:
        """Initialize Redis connection and start listening."""
        ...
    
    async def stop(self) -> None:
        """Clean up Redis connection."""
        ...
    
    async def subscribe_user_channel(self, user_id: str) -> AsyncIterator[str]:
        """Subscribe to a user's notification channel."""
        ...
    
    async def unsubscribe_user_channel(self, user_id: str) -> None:
        """Unsubscribe from a user's notification channel."""
        ...


class AuthValidatorProtocol(Protocol):
    """Validates JWT tokens for WebSocket connections."""
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token and return user claims."""
        ...
    
    def extract_user_id(self, claims: Dict[str, Any]) -> str:
        """Extract user ID from token claims."""
        ...
```

### 1.4 DI Provider Setup (di.py)

```python
"""Dependency injection configuration."""
from dishka import Provider, provide, Scope
from redis.asyncio import Redis
from fastapi import WebSocket

from .config import Settings
from .protocols import (
    ConnectionManagerProtocol,
    RedisSubscriberProtocol,
    AuthValidatorProtocol,
)
from .implementations.connection_manager import ConnectionManagerImpl
from .implementations.redis_subscriber import RedisSubscriberImpl
from .implementations.auth_validator import AuthValidatorImpl


class WebSocketServiceProvider(Provider):
    """DI provider for WebSocket service dependencies."""
    
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return Settings()
    
    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> Redis:
        """Provide Redis client for pub/sub."""
        client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            health_check_interval=30,
        )
        # Verify connection
        await client.ping()
        return client
    
    @provide(scope=Scope.APP)
    def provide_connection_manager(self) -> ConnectionManagerProtocol:
        """Provide WebSocket connection manager."""
        return ConnectionManagerImpl()
    
    @provide(scope=Scope.APP)
    async def provide_redis_subscriber(
        self,
        redis_client: Redis,
        connection_manager: ConnectionManagerProtocol,
        settings: Settings,
    ) -> RedisSubscriberProtocol:
        """Provide Redis subscriber."""
        subscriber = RedisSubscriberImpl(
            redis_client=redis_client,
            connection_manager=connection_manager,
            channel_prefix=settings.WEBSOCKET_CHANNEL_PREFIX,
        )
        await subscriber.start()
        return subscriber
    
    @provide(scope=Scope.APP)
    def provide_auth_validator(self, settings: Settings) -> AuthValidatorProtocol:
        """Provide JWT authentication validator."""
        return AuthValidatorImpl(
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
```

---

## Phase 2: Core Implementation

### 2.1 FastAPI App Structure (main.py)

```python
"""WebSocket Service main application."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dishka.integrations.fastapi import setup_dishka, FromDishka
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import PlainTextResponse

from .startup_setup import create_di_container
from .routers import health_routes, websocket_routes
from .config import settings
from .protocols import RedisSubscriberProtocol


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    container = create_di_container()
    setup_dishka(container, app)
    
    # Store container for cleanup
    app.state.container = container
    
    yield
    
    # Shutdown
    async with container() as request_container:
        # Stop Redis subscriber
        try:
            subscriber = await request_container.get(RedisSubscriberProtocol)
            await subscriber.stop()
        except Exception as e:
            print(f"Failed to stop Redis subscriber: {e}")
        
        # Close Redis connection
        try:
            from redis.asyncio import Redis
            redis_client = await request_container.get(Redis)
            await redis_client.close()
        except Exception as e:
            print(f"Failed to close Redis client: {e}")


app = FastAPI(
    title="HuleEdu WebSocket Service",
    description="Dedicated WebSocket service for real-time notifications",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_routes.router)
app.include_router(websocket_routes.router)


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

### 2.2 JWT Authentication Implementation (implementations/auth_validator.py)

```python
"""JWT authentication validator implementation."""
from typing import Optional, Dict, Any
import jwt
from jwt import InvalidTokenError

from ..protocols import AuthValidatorProtocol
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket_service.auth")


class AuthValidatorImpl(AuthValidatorProtocol):
    """JWT token validation implementation."""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token and return user claims."""
        try:
            # Decode and verify token
            claims = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": True},
            )
            
            # Verify required claims
            if "sub" not in claims:
                logger.warning("Token missing 'sub' claim")
                return None
            
            logger.info(f"Token validated for user: {claims.get('sub')}")
            return claims
            
        except InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    def extract_user_id(self, claims: Dict[str, Any]) -> str:
        """Extract user ID from token claims."""
        return str(claims.get("sub", ""))
```

### 2.3 WebSocket Endpoint (routers/websocket_routes.py)

```python
"""WebSocket routes."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from dishka.integrations.fastapi import FromDishka

from ..protocols import (
    ConnectionManagerProtocol,
    RedisSubscriberProtocol,
    AuthValidatorProtocol,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket_service.routes")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
    auth_validator: FromDishka[AuthValidatorProtocol],
    connection_manager: FromDishka[ConnectionManagerProtocol],
    redis_subscriber: FromDishka[RedisSubscriberProtocol],
):
    """WebSocket connection endpoint with JWT authentication."""
    # Validate token
    claims = await auth_validator.validate_token(token)
    if not claims:
        logger.warning(f"WebSocket connection rejected: invalid token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Extract user ID
    user_id = auth_validator.extract_user_id(claims)
    if not user_id:
        logger.warning("WebSocket connection rejected: no user ID in token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Accept connection
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for user: {user_id}")
    
    # Register connection
    await connection_manager.connect(websocket, user_id)
    
    # Create task for Redis subscription
    subscription_task = asyncio.create_task(
        handle_redis_messages(user_id, redis_subscriber)
    )
    
    try:
        # Keep connection alive and handle incoming messages
        while True:
            # We don't expect messages from client in this implementation
            # Just keep the connection open
            data = await websocket.receive_text()
            logger.debug(f"Received message from user {user_id}: {data}")
            
            # Echo back for connection testing
            await websocket.send_text(f"Echo: {data}")
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        # Clean up
        subscription_task.cancel()
        await connection_manager.disconnect(user_id)
        await redis_subscriber.unsubscribe_user_channel(user_id)


async def handle_redis_messages(
    user_id: str,
    redis_subscriber: RedisSubscriberProtocol,
) -> None:
    """Handle messages from Redis subscription."""
    try:
        async for message in redis_subscriber.subscribe_user_channel(user_id):
            logger.debug(f"Forwarding Redis message to user {user_id}: {message}")
    except asyncio.CancelledError:
        logger.debug(f"Redis subscription cancelled for user: {user_id}")
        raise
    except Exception as e:
        logger.error(f"Redis subscription error for user {user_id}: {e}")
```

### 2.4 Redis Pub/Sub Integration (implementations/redis_subscriber.py)

```python
"""Redis Pub/Sub subscriber implementation."""
import asyncio
from typing import AsyncIterator, Dict
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from ..protocols import RedisSubscriberProtocol, ConnectionManagerProtocol
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket_service.redis")


class RedisSubscriberImpl(RedisSubscriberProtocol):
    """Redis Pub/Sub subscription handler."""
    
    def __init__(
        self,
        redis_client: Redis,
        connection_manager: ConnectionManagerProtocol,
        channel_prefix: str = "ws:",
    ):
        self.redis_client = redis_client
        self.connection_manager = connection_manager
        self.channel_prefix = channel_prefix
        self.pubsub: Optional[PubSub] = None
        self.subscriptions: Dict[str, asyncio.Task] = {}
    
    async def start(self) -> None:
        """Initialize Redis connection and start listening."""
        self.pubsub = self.redis_client.pubsub()
        logger.info("Redis subscriber initialized")
    
    async def stop(self) -> None:
        """Clean up Redis connection."""
        # Cancel all subscription tasks
        for task in self.subscriptions.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self.subscriptions:
            await asyncio.gather(
                *self.subscriptions.values(),
                return_exceptions=True,
            )
        
        # Close pubsub
        if self.pubsub:
            await self.pubsub.close()
        
        logger.info("Redis subscriber stopped")
    
    async def subscribe_user_channel(self, user_id: str) -> AsyncIterator[str]:
        """Subscribe to a user's notification channel."""
        channel_name = f"{self.channel_prefix}{user_id}"
        
        # Create dedicated pubsub for this subscription
        user_pubsub = self.redis_client.pubsub()
        await user_pubsub.subscribe(channel_name)
        
        logger.info(f"Subscribed to channel: {channel_name}")
        
        try:
            async for message in user_pubsub.listen():
                if message["type"] == "message":
                    # Forward message to WebSocket
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    
                    await self.connection_manager.send_personal_message(data, user_id)
                    yield data
        finally:
            await user_pubsub.unsubscribe(channel_name)
            await user_pubsub.close()
            logger.info(f"Unsubscribed from channel: {channel_name}")
    
    async def unsubscribe_user_channel(self, user_id: str) -> None:
        """Unsubscribe from a user's notification channel."""
        # Handled in subscribe_user_channel finally block
        pass
```

### 2.5 Configuration (config.py)

```python
"""WebSocket service configuration."""
from __future__ import annotations
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

from common_core.config_enums import Environment


class Settings(BaseSettings):
    """Configuration settings for the WebSocket Service."""
    
    # Service identification
    SERVICE_NAME: str = "websocket_service"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8004
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Redis configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    WEBSOCKET_CHANNEL_PREFIX: str = "ws:"
    
    # JWT configuration
    JWT_SECRET_KEY: str = "your-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    
    # CORS configuration
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    
    # WebSocket configuration
    WEBSOCKET_HEARTBEAT_INTERVAL: int = 30  # seconds
    WEBSOCKET_CONNECTION_TIMEOUT: int = 60  # seconds
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="WEBSOCKET_SERVICE_",
    )


settings = Settings()
```

---

## Phase 3: Testing & Quality

### 3.1 Unit Tests with Protocol-Based Mocking

```python
# tests/unit/test_connection_manager.py
"""Unit tests for connection manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from websocket_service.implementations.connection_manager import ConnectionManagerImpl


@pytest.mark.asyncio
async def test_connect_adds_user_connection():
    """Test that connect properly stores user connection."""
    # Arrange
    manager = ConnectionManagerImpl()
    websocket = MagicMock()
    user_id = "user123"
    
    # Act
    await manager.connect(websocket, user_id)
    
    # Assert
    assert await manager.is_user_connected(user_id)


@pytest.mark.asyncio
async def test_send_personal_message():
    """Test sending message to connected user."""
    # Arrange
    manager = ConnectionManagerImpl()
    websocket = AsyncMock()
    user_id = "user123"
    message = "Test notification"
    
    await manager.connect(websocket, user_id)
    
    # Act
    await manager.send_personal_message(message, user_id)
    
    # Assert
    websocket.send_text.assert_called_once_with(message)
```

### 3.2 Integration Tests for Redis Pub/Sub

```python
# tests/integration/test_redis_pubsub.py
"""Integration tests for Redis pub/sub functionality."""
import pytest
import asyncio
from testcontainers.redis import RedisContainer
from redis.asyncio import Redis

from websocket_service.implementations.redis_subscriber import RedisSubscriberImpl
from websocket_service.implementations.connection_manager import ConnectionManagerImpl


@pytest.fixture(scope="module")
def redis_container():
    """Provide Redis container for testing."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.mark.asyncio
async def test_redis_message_forwarding(redis_container):
    """Test that Redis messages are forwarded to WebSocket."""
    # Setup Redis client
    redis_url = redis_container.get_connection_url()
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    
    # Setup components
    connection_manager = ConnectionManagerImpl()
    subscriber = RedisSubscriberImpl(
        redis_client=redis_client,
        connection_manager=connection_manager,
    )
    
    await subscriber.start()
    
    # Simulate WebSocket connection
    websocket = AsyncMock()
    user_id = "user123"
    await connection_manager.connect(websocket, user_id)
    
    # Subscribe to user channel
    subscription_task = asyncio.create_task(
        consume_messages(subscriber, user_id)
    )
    
    # Allow subscription to establish
    await asyncio.sleep(0.1)
    
    # Publish message to Redis
    test_message = '{"type": "notification", "content": "Test message"}'
    await redis_client.publish(f"ws:{user_id}", test_message)
    
    # Allow message to be processed
    await asyncio.sleep(0.1)
    
    # Verify message was sent to WebSocket
    websocket.send_text.assert_called_with(test_message)
    
    # Cleanup
    subscription_task.cancel()
    await subscriber.stop()
    await redis_client.close()


async def consume_messages(subscriber, user_id):
    """Helper to consume messages from subscription."""
    async for _ in subscriber.subscribe_user_channel(user_id):
        pass
```

### 3.3 Contract Tests for Message Formats

```python
# tests/contract/test_message_formats.py
"""Contract tests for WebSocket message formats."""
import json
import pytest
from pydantic import ValidationError

from websocket_service.models.responses import (
    WebSocketMessage,
    NotificationMessage,
    ErrorMessage,
)


def test_notification_message_serialization():
    """Test notification message serialization."""
    # Create message
    message = NotificationMessage(
        type="notification",
        event_type="batch_completed",
        data={"batch_id": "123", "status": "completed"},
    )
    
    # Serialize
    json_str = message.model_dump_json()
    
    # Deserialize
    parsed = json.loads(json_str)
    
    # Verify structure
    assert parsed["type"] == "notification"
    assert parsed["event_type"] == "batch_completed"
    assert parsed["data"]["batch_id"] == "123"


def test_error_message_format():
    """Test error message format."""
    message = ErrorMessage(
        type="error",
        code="AUTH_FAILED",
        message="Authentication failed",
    )
    
    json_data = json.loads(message.model_dump_json())
    
    assert json_data["type"] == "error"
    assert json_data["code"] == "AUTH_FAILED"
    assert json_data["message"] == "Authentication failed"
```

---

## Phase 4: Infrastructure

### 4.1 Dockerfile

```dockerfile
FROM python:3.11-slim

# Install PDM
RUN pip install pdm

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml pdm.lock ./

# Install dependencies
RUN pdm sync --prod --no-self

# Copy service code
COPY . .

# Install the service itself
RUN pdm install --prod

# Set Python path
ENV PYTHONPATH=/app

# Expose WebSocket port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pdm run python -c "import httpx; httpx.get('http://localhost:8004/healthz').raise_for_status()"

# Start service
CMD ["pdm", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
```

### 4.2 Docker Compose Entry

```yaml
# In docker-compose.services.yml
websocket_service:
  build:
    context: ./services/websocket_service
    dockerfile: Dockerfile
  container_name: huleedu_websocket_service
  restart: unless-stopped
  depends_on:
    - redis
  networks:
    - huleedu_internal_network
  ports:
    - "8004:8004"
  environment:
    - WEBSOCKET_SERVICE_ENVIRONMENT=development
    - WEBSOCKET_SERVICE_LOG_LEVEL=INFO
    - WEBSOCKET_SERVICE_REDIS_URL=redis://redis:6379/0
    - WEBSOCKET_SERVICE_JWT_SECRET_KEY=${JWT_SECRET_KEY}
    - WEBSOCKET_SERVICE_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8004/healthz"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
```

### 4.3 Environment Configuration

```bash
# .env.example for websocket_service
WEBSOCKET_SERVICE_ENVIRONMENT=development
WEBSOCKET_SERVICE_LOG_LEVEL=INFO
WEBSOCKET_SERVICE_REDIS_URL=redis://localhost:6379/0
WEBSOCKET_SERVICE_JWT_SECRET_KEY=your-secret-key-here
WEBSOCKET_SERVICE_ALLOWED_ORIGINS=["http://localhost:3000"]
WEBSOCKET_SERVICE_HOST=0.0.0.0
WEBSOCKET_SERVICE_PORT=8004
```

### 4.4 Service Startup Scripts

```python
# startup_setup.py
"""Service startup configuration."""
from dishka import make_async_container
from huleedu_service_libs.observability import setup_observability
from huleedu_service_libs.logging_utils import configure_service_logging

from .di import WebSocketServiceProvider
from .config import settings


def create_di_container():
    """Create and configure DI container."""
    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        log_level=settings.LOG_LEVEL,
    )
    
    # Create container
    container = make_async_container(WebSocketServiceProvider())
    
    # Setup observability
    setup_observability(container, service_name=settings.SERVICE_NAME)
    
    return container
```

---

## Implementation Checklist

### Phase 1: Service Creation
- [ ] Create service directory structure
- [ ] Initialize PDM project with dependencies
- [ ] Define all protocol interfaces
- [ ] Setup DI provider configuration

### Phase 2: Core Features
- [ ] Implement FastAPI application with lifespan management
- [ ] Create JWT authentication validator
- [ ] Implement WebSocket connection manager
- [ ] Build Redis Pub/Sub subscriber
- [ ] Create WebSocket endpoint with auth

### Phase 3: Testing
- [ ] Write unit tests for all components
- [ ] Create integration tests with testcontainers
- [ ] Implement contract tests for message formats
- [ ] Add health endpoint tests
- [ ] Verify authentication flow

### Phase 4: Infrastructure
- [ ] Create Dockerfile with health checks
- [ ] Add service to docker-compose.services.yml
- [ ] Configure environment variables
- [ ] Setup Prometheus metrics
- [ ] Document deployment process

### Phase 5: Migration (Atomic Operation)
- [ ] Remove WebSocket routes from api_gateway_service
- [ ] Delete WebSocket tests from api_gateway_service
- [ ] Update frontend WebSocket connection URL
- [ ] Run full test suite
- [ ] Deploy and verify end-to-end

---

## Critical Implementation Notes

1. **Authentication**: JWT tokens passed as query parameters (ws://host/ws?token=xxx)
2. **Message Flow**: Backend services → Redis Pub/Sub → WebSocket Service → Client
3. **Channel Pattern**: Redis channels use format `ws:{user_id}`
4. **Error Handling**: Invalid tokens result in WebSocket close with code 1008
5. **Health Checks**: Service exposes /healthz and /metrics endpoints
6. **Scaling**: Service designed to scale horizontally with Redis as backplane
7. **Testing**: All tests use protocol-based mocking per HuleEdu standards
8. **Observability**: Integrated logging, metrics, and distributed tracing

This implementation follows all HuleEdu architectural patterns and provides a clean, scalable WebSocket service.