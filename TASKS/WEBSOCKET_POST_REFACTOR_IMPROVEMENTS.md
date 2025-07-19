# WebSocket Service Post-Refactor Improvements

## Overview
This document outlines critical improvements needed after the WebSocket refactor completion. These tasks address test coverage gaps, error handling standardization, documentation updates, and observability enhancements.

## Priority 1: Implement HuleeduError Pattern

### Discovery: Existing Error Handling Infrastructure

The HuleEdu codebase **already has a comprehensive error handling system** in `huleedu_service_libs`:

1. **HuleEduError Class** (`huleedu_service_libs.error_handling.huleedu_error`)
   - Wraps `ErrorDetail` model with automatic OpenTelemetry integration
   - Auto-records errors to current span
   - Provides convenient property access

2. **Factory Pattern** (`huleedu_service_libs.error_handling.factories`)
   - Pre-built factories for all generic error codes
   - Service-specific factories for domain errors
   - Consistent error creation with context capture

3. **HTTP Status Mapping** (`huleedu_service_libs.error_handling.quart_handlers`)
   - `ERROR_CODE_TO_HTTP_STATUS` dictionary maps all error codes
   - Quart error handlers already exist (need FastAPI equivalent)

4. **No New Error Codes Needed**
   - Existing `ErrorCode` enum covers all WebSocket/Gateway scenarios
   - `AUTHENTICATION_ERROR`, `CONNECTION_ERROR`, `RATE_LIMIT`, etc. are sufficient

### Required Changes

#### WebSocket Service Implementation

1. **Update JWT Validator** (`implementations/jwt_validator.py`):
   ```python
   from huleedu_service_libs.error_handling import raise_authentication_error
   from uuid import uuid4
   
   async def validate_token(self, token: str) -> str:
       correlation_id = uuid4()  # Or extract from context
       try:
           payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
           
           # Check expiration
           if 'exp' not in payload:
               raise_authentication_error(
                   service="websocket_service",
                   operation="validate_token",
                   message="Token missing expiration claim",
                   correlation_id=correlation_id,
                   reason="missing_exp"
               )
           
           # Return user_id
           return payload.get('sub')
           
       except jwt.ExpiredSignatureError:
           raise_authentication_error(
               service="websocket_service",
               operation="validate_token",
               message="Token has expired",
               correlation_id=correlation_id,
               reason="jwt_expired"
           )
       except jwt.InvalidTokenError as e:
           raise_authentication_error(
               service="websocket_service",
               operation="validate_token",
               message=f"Invalid token: {str(e)}",
               correlation_id=correlation_id,
               reason="jwt_invalid"
           )
   ```

2. **Update WebSocket Routes** (`routers/websocket_routes.py`):
   ```python
   import json
   from huleedu_service_libs.error_handling import HuleEduError
   
   @router.websocket("/ws")
   async def websocket_endpoint(...):
       try:
           # Validate token
           user_id = await jwt_validator.validate_token(token)
       except HuleEduError as e:
           # Serialize error for WebSocket close reason (max 123 bytes)
           error_json = json.dumps({
               "error_code": e.error_code,
               "message": e.error_detail.message[:50],  # Truncate for size
               "correlation_id": str(e.correlation_id)
           })
           await websocket.close(
               code=status.WS_1008_POLICY_VIOLATION,
               reason=error_json[:123]
           )
           return
       
       # Handle connection limits
       try:
           success = await websocket_manager.connect(websocket, user_id)
           if not success:
               from huleedu_service_libs.error_handling import raise_quota_exceeded
               raise_quota_exceeded(
                   service="websocket_service",
                   operation="websocket_connect",
                   quota_type="concurrent_connections",
                   limit=settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER,
                   message=f"User {user_id} exceeded connection limit",
                   correlation_id=correlation_id
               )
       except HuleEduError as e:
           error_json = json.dumps({
               "error_code": e.error_code,
               "message": "Connection limit exceeded"
           })
           await websocket.close(code=4000, reason=error_json[:123])
           return
   ```

3. **Update Message Listener** (`implementations/message_listener.py`):
   ```python
   from huleedu_service_libs.error_handling import (
       raise_connection_error,
       raise_external_service_error
   )
   
   async def _redis_listener(self, ...):
       try:
           async for pubsub in self.redis_client.subscribe(channel):
               # ... existing logic ...
       except ConnectionError as e:
           raise_connection_error(
               service="websocket_service",
               operation="redis_subscribe",
               target="redis",
               message=f"Redis connection failed: {str(e)}",
               correlation_id=correlation_id
           )
       except Exception as e:
           await websocket.close(code=1011)  # Internal error
           raise_external_service_error(
               service="websocket_service",
               operation="redis_listener",
               external_service="redis",
               message=f"Unexpected error in Redis listener: {str(e)}",
               correlation_id=correlation_id
           )
   ```

#### API Gateway Service Implementation

1. **Update Auth Module** (`auth.py`):
   ```python
   from huleedu_service_libs.error_handling import raise_authentication_error
   
   async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
       try:
           payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
           # ... existing validation ...
       except jwt.ExpiredSignatureError:
           raise_authentication_error(
               service="api_gateway_service",
               operation="validate_jwt",
               message="Token has expired",
               correlation_id=getattr(request.state, "correlation_id", uuid4()),
               reason="jwt_expired"
           )
       except jwt.JWTError:
           raise_authentication_error(
               service="api_gateway_service",
               operation="validate_jwt",
               message="Could not validate credentials",
               correlation_id=getattr(request.state, "correlation_id", uuid4())
           )
   ```

2. **Update Status Routes** (`routers/status_routes.py`):
   ```python
   from huleedu_service_libs.error_handling import (
       raise_authentication_error,
       raise_resource_not_found,
       raise_external_service_error
   )
   
   @router.get("/batches/{batch_id}/status")
   async def get_batch_status(...):
       try:
           # ... existing logic ...
           
           # Ownership check
           if data.get("user_id") != user_id:
               raise_authentication_error(
                   service="api_gateway_service",
                   operation="get_batch_status",
                   message="Ownership violation: batch does not belong to user",
                   correlation_id=correlation_id,
                   batch_id=batch_id,
                   requested_by=user_id,
                   actual_owner=data.get("user_id")
               )
               
       except HTTPStatusError as e:
           if e.response.status_code == 404:
               raise_resource_not_found(
                   service="api_gateway_service",
                   operation="get_batch_status",
                   resource_type="batch",
                   resource_id=batch_id,
                   correlation_id=correlation_id
               )
           else:
               raise_external_service_error(
                   service="api_gateway_service",
                   operation="get_batch_status",
                   external_service="result_aggregator",
                   message=f"Downstream service error: {e.response.text}",
                   correlation_id=correlation_id,
                   status_code=e.response.status_code
               )
   ```

#### Create FastAPI Error Handler

Create new file: `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/fastapi_handlers.py`

```python
"""
FastAPI integration for HuleEdu error handling.
"""
from typing import Any, Dict
from uuid import uuid4

from common_core.error_enums import ErrorCode
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError
from .logging_utils import format_error_for_logging
from .quart_handlers import ERROR_CODE_TO_HTTP_STATUS

import logging
logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register error handlers with a FastAPI application."""
    
    @app.exception_handler(HuleEduError)
    async def huleedu_error_handler(request: Request, exc: HuleEduError):
        # Log the error
        log_context = format_error_for_logging(exc.error_detail)
        logger.error("HuleEduError occurred", extra=log_context, exc_info=True)
        
        # Get HTTP status
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(
            exc.error_detail.error_code, 500
        )
        
        # Create response
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.error_detail.error_code.value,
                    "message": exc.error_detail.message,
                    "correlation_id": str(exc.error_detail.correlation_id),
                    "service": exc.error_detail.service,
                    "timestamp": exc.error_detail.timestamp.isoformat(),
                    "details": exc.error_detail.details,
                }
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        
        # Extract first validation error
        errors = exc.errors()
        first_error = errors[0] if errors else {"msg": "Validation failed"}
        
        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=first_error.get("msg", "Invalid request"),
            service=app.title.lower().replace(" ", "_"),
            operation=f"{request.method} {request.url.path}",
            correlation_id=correlation_id,
            details={"validation_errors": errors}
        )
        
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": error_detail.error_code.value,
                    "message": error_detail.message,
                    "correlation_id": str(error_detail.correlation_id),
                    "service": error_detail.service,
                    "timestamp": error_detail.timestamp.isoformat(),
                    "details": error_detail.details,
                }
            }
        )
    
    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        
        logger.exception(
            "Unexpected error occurred",
            extra={
                "error.type": type(exc).__name__,
                "error.message": str(exc),
                "correlation_id": str(correlation_id),
            }
        )
        
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.UNKNOWN_ERROR.value,
                    "message": "An unexpected error occurred",
                    "correlation_id": str(correlation_id),
                    "service": app.title.lower().replace(" ", "_"),
                    "timestamp": create_error_detail_with_context(
                        error_code=ErrorCode.UNKNOWN_ERROR,
                        message=str(exc),
                        service=app.title.lower().replace(" ", "_"),
                        operation="handle_unexpected_error",
                        correlation_id=correlation_id,
                    ).timestamp.isoformat(),
                    "details": {"error_type": type(exc).__name__},
                }
            }
        )


def extract_correlation_id(request: Request) -> str:
    """Extract or generate correlation ID from request."""
    # Try state first (set by middleware)
    if hasattr(request.state, "correlation_id"):
        return str(request.state.correlation_id)
    
    # Try header
    correlation_id = request.headers.get("X-Correlation-ID")
    
    # Try query parameter
    if not correlation_id:
        correlation_id = request.query_params.get("correlation_id")
    
    # Generate new
    if not correlation_id:
        correlation_id = str(uuid4())
    
    return correlation_id
```

### Implementation Notes

1. **No New Error Codes** - Use existing ErrorCode enum values
2. **Correlation ID Flow** - Extract from request.state or generate new
3. **WebSocket Errors** - Serialize ErrorDetail to JSON in close reason
4. **Auto-Tracing** - HuleEduError automatically records to OpenTelemetry spans
5. **Consistent Factories** - Use existing factory functions for all errors

## Priority 2: Increase WebSocket Service Test Coverage

### Current Coverage: 75% (Target: >90%)

#### Files Needing Tests
1. **di.py (0% coverage)**
   - Test DI container creation
   - Test provider lifecycle methods
   - Test Redis client start/stop

2. **main.py (0% coverage)**
   - Integration test for app startup
   - Test health check accessibility
   - Test metrics endpoint

3. **protocols.py (63% coverage)**
   - Add tests for protocol implementations
   - Cover edge cases in abstract methods

4. **Error paths in implementations**
   - JWT validation edge cases
   - Redis connection failures
   - WebSocket disconnection scenarios

### Test Implementation Strategy
```python
# Integration test example for main.py
async def test_websocket_service_startup():
    """Test that the WebSocket service starts correctly."""
    from services.websocket_service.main import app
    from httpx import AsyncClient
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

## Priority 3: Update API Gateway Documentation

### Files to Update
1. **services/api_gateway_service/README.md**
   - Remove ACL transformation references (line 76)
   - Update status endpoint description
   - Clarify that RAS handles BOS fallback internally

2. **services/api_gateway_service/routers/status_routes.py**
   - Update docstring to reflect no ACL transformation
   - Document that this is a pure proxy endpoint

### Documentation Updates
```markdown
## API Endpoints

### Batch Management

- `GET /v1/batches/{batch_id}/status` - Get batch status with ownership validation
  - Proxies to Result Aggregator Service
  - Enforces user ownership based on JWT claims
  - No data transformation performed
```

## Priority 4: Add OpenTelemetry Span Creation

### Discovery: Existing Observability Integration

1. **HuleEduError Auto-Tracing**
   - The `HuleEduError` class automatically records exceptions to the current span
   - Sets error status and attributes on span
   - No manual span recording needed for errors

2. **Existing Patterns**
   - `huleedu_service_libs.observability.trace_operation` for wrapping operations
   - Automatic trace propagation via middleware
   - Context injection/extraction for event system

### WebSocket Service Implementation

1. **Update startup_setup.py**:
   ```python
   from huleedu_service_libs import init_tracing
   from huleedu_service_libs.middleware.frameworks.fastapi_middleware import setup_tracing_middleware
   
   def setup_tracing(app: FastAPI) -> None:
       """Initialize distributed tracing."""
       logger.info("Initializing distributed tracing...")
       
       if not TRACING_AVAILABLE:
           logger.warning("OpenTelemetry dependencies not available, skipping tracing setup")
           return
       
       # Initialize tracer
       app.tracer = init_tracing("websocket_service")
       
       # Setup middleware
       setup_tracing_middleware(app, app.tracer)
       
       logger.info("Distributed tracing initialized successfully")
   ```

2. **Add spans to WebSocket routes** (`routers/websocket_routes.py`):
   ```python
   from huleedu_service_libs.observability import trace_operation
   
   @router.websocket("/ws")
   async def websocket_endpoint(
       websocket: WebSocket,
       token: str = Query(None),
       jwt_validator: FromDishka[JWTValidatorProtocol],
       websocket_manager: FromDishka[WebSocketManagerProtocol],
       message_listener: FromDishka[MessageListenerProtocol],
   ) -> None:
       tracer = websocket.app.tracer  # Get tracer from app
       correlation_id = uuid4()
       
       # Trace token validation
       with trace_operation(tracer, "websocket.validate_token", {
           "has_token": bool(token),
           "correlation_id": str(correlation_id)
       }):
           try:
               user_id = await jwt_validator.validate_token(token)
           except HuleEduError as e:
               # Error automatically recorded to span
               # ... handle error ...
       
       # Trace connection
       with trace_operation(tracer, "websocket.connect", {
           "user.id": user_id,
           "correlation_id": str(correlation_id)
       }):
           success = await websocket_manager.connect(websocket, user_id)
       
       # Trace message listening
       with trace_operation(tracer, "websocket.listen", {
           "user.id": user_id,
           "channel": f"ws:{user_id}"
       }):
           await message_listener.start_listening(user_id, websocket)
   ```

3. **Add spans to message listener** (`implementations/message_listener.py`):
   ```python
   from huleedu_service_libs.observability import trace_operation
   
   async def _redis_listener(self, ...):
       tracer = trace.get_tracer(__name__)
       
       async for pubsub in self.redis_client.subscribe(channel):
           while True:
               message = await pubsub.get_message(...)
               if message and message.get("type") == "message":
                   # Trace message processing
                   with trace_operation(tracer, "websocket.forward_message", {
                       "user.id": user_id,
                       "message.size": len(message["data"])
                   }):
                       await self.websocket_manager.send_message_to_user(
                           user_id, 
                           message["data"].decode("utf-8")
                       )
   ```

### API Gateway Service Implementation

1. **Spans already exist via middleware** - FastAPI instrumentor adds automatic spans
2. **Add custom spans for business operations**:
   ```python
   from huleedu_service_libs.observability import trace_operation, inject_trace_context
   
   @router.post("/batches/{batch_id}/pipelines")
   async def request_pipeline_execution(...):
       tracer = request.app.tracer
       
       # Trace Kafka publish
       with trace_operation(tracer, "gateway.publish_command", {
           "batch.id": batch_id,
           "pipeline": request.pipeline.value,
           "user.id": user_id
       }):
           # Inject trace context for propagation
           metadata = {}
           inject_trace_context(metadata)
           
           envelope = EventEnvelope(
               event_type=topic_name(EventTopic.BATCH_PIPELINE_COMMANDS),
               # ... other fields ...
               metadata=metadata  # Trace context included
           )
           
           await kafka_bus.publish(topic, envelope.model_dump_json())
   ```

3. **Trace downstream calls**:
   ```python
   with trace_operation(tracer, "gateway.proxy_request", {
       "target.service": "result_aggregator",
       "operation": "get_batch_status",
       "batch.id": batch_id
   }):
       response = await http_client.get(aggregator_url)
   ```

### Implementation Notes

1. **Error Tracing is Automatic** - HuleEduError records to span automatically
2. **Use trace_operation** - For wrapping critical operations
3. **Propagate Context** - Use inject_trace_context for event system
4. **Business Attributes Only** - Never include PII in span attributes
5. **Leverage Middleware** - FastAPI/Quart middleware handles HTTP spans

## Priority 5: Additional Improvements

### WebSocket Service Enhancements
1. **Configurable channel prefix**
   ```python
   WEBSOCKET_CHANNEL_PREFIX = settings.WEBSOCKET_CHANNEL_PREFIX or "ws:"
   ```

2. **Connection timeout handling**
   ```python
   WEBSOCKET_IDLE_TIMEOUT = settings.WEBSOCKET_IDLE_TIMEOUT or 300  # 5 minutes
   ```

3. **Prometheus metrics registration**
   - Ensure WebSocketMetrics registers with container registry
   - Add connection duration histogram
   - Track message sizes

4. **Graceful shutdown**
   - Close all WebSocket connections on SIGTERM
   - Ensure Redis listeners are cancelled

### API Gateway Improvements
1. **Request size limits for file uploads**
   ```python
   MAX_UPLOAD_SIZE = settings.MAX_UPLOAD_SIZE or 100 * 1024 * 1024  # 100MB
   ```

2. **Consistent error response format**
   - All errors should return ErrorDetail structure
   - Include request ID in error responses

## Implementation Plan

### Phase 1: Error Handling (2-3 hours)
1. Implement HuleeduError in WebSocket service
2. Update API Gateway error handling
3. Add comprehensive error tests

### Phase 2: Test Coverage (3-4 hours)
1. Add integration tests for main.py
2. Test DI container setup
3. Cover all error paths
4. Achieve >90% coverage

### Phase 3: Documentation (1 hour)
1. Update API Gateway README
2. Remove outdated ACL references
3. Document new error patterns

### Phase 4: Observability (2-3 hours)
1. Add OpenTelemetry spans
2. Register Prometheus metrics
3. Test trace propagation

### Phase 5: Enhancements (2 hours)
1. Add configurable settings
2. Implement connection timeouts
3. Add graceful shutdown

## Validation Checklist

- [ ] All errors use HuleeduError pattern
- [ ] Test coverage >90% for WebSocket service
- [ ] No ACL references in API Gateway docs
- [ ] OpenTelemetry spans properly configured
- [ ] Prometheus metrics registered and working
- [ ] Connection timeouts implemented
- [ ] Graceful shutdown tested
- [ ] Error responses include correlation IDs
- [ ] All settings are configurable
- [ ] Integration tests pass

## Success Metrics

1. **Test Coverage**: WebSocket service >90%
2. **Error Standardization**: 100% HuleeduError usage
3. **Observability**: All operations have spans
4. **Documentation**: Accurate and up-to-date
5. **Reliability**: Graceful handling of all failure modes

## Key Discoveries Summary

### Error Handling Infrastructure
1. **HuleEduError Already Exists** - Complete implementation in `huleedu_service_libs`
   - Automatic OpenTelemetry integration
   - Structured error responses
   - Factory pattern for consistent error creation

2. **No New Error Codes Needed**
   - Existing `ErrorCode` enum covers all scenarios
   - `AUTHENTICATION_ERROR`, `CONNECTION_ERROR`, `RATE_LIMIT` are sufficient
   - Avoid "exception creep" by reusing existing codes

3. **FastAPI Handler Missing** - Only component that needs creation
   - Mirror the existing Quart handler pattern
   - Use same `ERROR_CODE_TO_HTTP_STATUS` mapping

### Observability Infrastructure
1. **Auto-Tracing in Errors** - HuleEduError automatically records to spans
2. **Existing Helpers** - `trace_operation`, `inject_trace_context` ready to use
3. **Middleware Integration** - HTTP spans handled automatically

### Implementation Strategy
1. **Use Existing Factories** - Don't create new error creation patterns
2. **Leverage Auto-Features** - Error tracing, context capture are automatic
3. **Minimal New Code** - Only FastAPI handler and service-specific usage

## Notes

- Follow existing patterns from other services
- Use agents for complex implementation tasks
- Test all changes thoroughly
- Update documentation as you go
- Ensure backward compatibility for frontend clients
- **Important**: The error handling and observability infrastructure is mature - use it, don't reinvent it

## Update: API Gateway Authentication Issue

During implementation, a critical issue was discovered with Dishka + FastAPI authentication integration:
- Mixing `FromDishka[]` with `Depends()` causes parameter validation errors
- See `/TASKS/API_GATEWAY_DISHKA_AUTH_SESSION_PROMPT.md` for next session
- The API Gateway needs a clean authentication solution before other improvements