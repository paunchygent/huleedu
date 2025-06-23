# Implementation Guide: HuleEdu Client Interface Layer (2/3)

This document provides a step-by-step implementation plan for the API Gateway component of the client interface layer.

## 🚫 **BLOCKING DEPENDENCY - REFACTORING REQUIRED**

**⚠️ CRITICAL: This task is BLOCKED until completion of:**

📋 **[LEAN_BATCH_REGISTRATION_REFACTORING.md](LEAN_BATCH_REGISTRATION_REFACTORING.md)**

**Reason**: API Gateway endpoints reference batch registration models that need to be refactored for lean registration and proper service boundaries.

## Part 2: API Gateway Service Implementation

This part covers the creation of the new FastAPI-based `api_gateway_service`, which will serve as the primary entry point for the React frontend. It builds upon the foundational work completed in Part 1 (documentation/TASKS/API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_1.md) and which will be completed in Part 3 (documentation/TASKS/API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md).

### Checkpoint 2.1: API Gateway Service Foundation

**Objective**: Create the skeleton for the `api_gateway_service`, including its directory structure, dependencies, and Docker configuration, adhering to rule `041-fastapi-integration-patterns.mdc`.

**Affected Files**:

- New service directory: `services/api_gateway_service/`
- `docker-compose.services.yml`: To add the new service container.

**Implementation Steps**:

1. **Create Service Structure**: Create the new service directory `services/api_gateway_service/` with the following structure. This differs from our Quart services and must follow the FastAPI router pattern.

    ```
    services/api_gateway_service/
    ├── main.py             # FastAPI app instantiation and startup logic
    ├── di.py               # Dishka dependency injection providers
    ├── config.py           # Pydantic settings
    ├── auth.py             # Reusable authentication dependencies
    ├── pyproject.toml
    ├── Dockerfile
    └── routers/
        ├── __init__.py
        ├── pipeline_routes.py
        └── status_routes.py
    ```

2. **Define Dependencies**: Create the `pyproject.toml` file. This includes `fastapi`, `uvicorn` for serving, `dishka[fastapi]` for DI, and `slowapi` for rate limiting.

    **File**: `services/api_gateway_service/pyproject.toml`

    ```toml
    [project]
    name = "huleedu-api-gateway-service"
    version = "1.0.0"
    description = "HuleEdu API Gateway for client-facing interactions"
    dependencies = [
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "dishka[fastapi]>=1.3.0",
        "python-jose[cryptography]", # For JWT
        "passlib[bcrypt]",           # For password hashing (future)
        "huleedu-common-core",
        "huleedu-service-libs",
        "slowapi",                   # For rate limiting
    ]

    [tool.pdm.scripts]
    start = "uvicorn services.api_gateway_service.main:app --host 0.0.0.0 --port 4001"
    dev = "uvicorn services.api_gateway_service.main:app --host 0.0.0.0 --port 4001 --reload"

    # ... other standard tool sections like mypy, ruff ...
    ```

3. **Create Dockerfile**: The Dockerfile will use `uvicorn` as the entry point.

    **File**: `services/api_gateway_service/Dockerfile`

    ```dockerfile
    FROM python:3.11-slim

    ENV PYTHONUNBUFFERED=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONPATH=/app \
        ENV_TYPE=docker \
        PDM_USE_VENV=false

    WORKDIR /app

    RUN pip install --no-cache-dir pdm

    COPY common_core/ /app/common_core/
    COPY services/libs/ /app/services/libs/
    COPY services/api_gateway_service/ /app/services/api_gateway_service/

    WORKDIR /app/services/api_gateway_service
    RUN pdm install --prod

    RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser
    USER appuser

    EXPOSE 4001
    CMD ["pdm", "run", "start"]
    ```

4. **Define Configuration**: Create `config.py` for environment-based settings, including specific CORS origins for our React frontend.

    **File**: `services/api_gateway_service/config.py`

    ```python
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env", env_prefix="API_GATEWAY_", case_sensitive=False
        )

        # Service identity
        SERVICE_NAME: str = "api-gateway-service"
        LOG_LEVEL: str = Field(default="INFO")

        # CORS configuration for React frontend
        CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"] # Vite/CRA defaults

        # Kafka configuration
        KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"

        # Internal Service URLs
        RESULT_AGGREGATOR_URL: str = "http://result_aggregator_service:8000"

        # Security
        JWT_SECRET_KEY: str = "a-very-secret-key-that-must-be-in-secrets-manager"
        JWT_ALGORITHM: str = "HS256"

    settings = Settings()
    ```

**Done When**:

- ✅ The `api_gateway_service` directory and file structure are created as specified.
- ✅ The service is added to `docker-compose.services.yml` and starts successfully with `docker compose up`.

### Checkpoint 2.2: Implement Authentication & Command Endpoint (Hardened)

**Objective**: Secure the gateway with production-grade authentication and implement the primary endpoint for initiating backend workflows, incorporating critical architect feedback for security and reliability.

**Affected Files**:

- `services/api_gateway_service/auth.py` (new)
- `services/api_gateway_service/routers/pipeline_routes.py` (new)
- `services/api_gateway_service/main.py` (new)
- `services/api_gateway_service/di.py` (new)
- `services/api_gateway_service/middleware/rate_limit_middleware.py` (new)

**Implementation Steps**:

1. **Create Hardened Authentication Dependency**: Implement JWT validation with expiry checks and comprehensive error handling.

    **File**: `services/api_gateway_service/auth.py`

    ```python
    from datetime import datetime, timezone
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer
    import jwt
    from .config import settings

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")

    async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
        """
        Validate JWT token with expiry check and comprehensive error handling.
        
        CRITICAL: Implements architect feedback #2 for JWT expiry validation.
        """
        try:
            # Decode and validate JWT
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # CRITICAL: Validate token expiry (Architect Feedback #2)
            exp_timestamp = payload.get("exp")
            if exp_timestamp is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Token missing expiration claim"
                )
            
            current_time = datetime.now(timezone.utc).timestamp()
            if current_time >= exp_timestamp:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired"
                )
            
            # Extract user ID
            user_id: str | None = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Invalid token payload: missing subject"
                )
                
            return user_id
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}"
            )
        except Exception as e:
            # Log unexpected errors but don't expose internal details
            logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed"
            )
    ```

2. **Implement Rate Limiting Middleware**: Add protection against API abuse and accidental floods.

    **File**: `services/api_gateway_service/middleware/rate_limit_middleware.py`

    ```python
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from fastapi import Request, Response
    import redis.asyncio as redis

    # CRITICAL: Rate limiting to protect against abuse (Architect Feedback #3)
    def create_limiter() -> Limiter:
        """Create rate limiter with Redis backend for distributed limiting."""
        return Limiter(
            key_func=get_remote_address,
            storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            default_limits=["100/minute"]  # Global default
        )

    limiter = create_limiter()

    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        """Custom rate limit exceeded handler with proper logging."""
        client_ip = get_remote_address(request)
        logger.warning(f"Rate limit exceeded for IP: {client_ip}, limit: {exc.detail}")
        
        response = Response(
            content=f"Rate limit exceeded: {exc.detail}",
            status_code=429,
            headers={"Retry-After": str(exc.retry_after) if exc.retry_after else "60"}
        )
        return response
    ```

3. **Implement DI Providers with Graceful Shutdown**: Set up dependencies with proper lifecycle management.

    **File**: `services/api_gateway_service/di.py`

    ```python
    from aiohttp import ClientSession, ClientTimeout
    from dishka import Provider, Scope, provide
    from huleedu_service_libs.kafka_client import KafkaBus
    from huleedu_service_libs.logging_utils import create_service_logger
    from .config import settings

    logger = create_service_logger("api_gateway.di")

    class ApiGatewayProvider(Provider):
        scope = Scope.APP

        @provide
        async def provide_kafka_bus(self) -> KafkaBus:
            """Provide Kafka bus with proper lifecycle management."""
            bus = KafkaBus(
                client_id=settings.SERVICE_NAME, 
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
            )
            await bus.start()
            logger.info("Kafka bus started")
            return bus

        @provide
        async def provide_http_session(self) -> ClientSession:
            """
            Provide HTTP session with configured timeouts.
            
            CRITICAL: Properly configured timeouts prevent indefinite hangs
            when querying internal services (Architect Feedback #6).
            """
            timeout = ClientTimeout(
                total=settings.HTTP_CLIENT_TIMEOUT_SECONDS,
                connect=settings.HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS
            )
            session = ClientSession(timeout=timeout)
            logger.info("HTTP session created with configured timeouts")
            return session

        async def finalize_kafka_bus(self, kafka_bus: KafkaBus) -> None:
            """CRITICAL: Graceful shutdown to prevent resource leaks (Architect Feedback #4)."""
            try:
                await kafka_bus.stop()
                logger.info("Kafka bus stopped gracefully")
            except Exception as e:
                logger.error(f"Error stopping Kafka bus: {e}", exc_info=True)

        async def finalize_http_session(self, http_session: ClientSession) -> None:
            """CRITICAL: Graceful shutdown to prevent resource leaks (Architect Feedback #4)."""
            try:
                await http_session.close()
                logger.info("HTTP session closed gracefully")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {e}", exc_info=True)
    ```

4. **Implement the Hardened Command Endpoint Router**:

    **File**: `services/api_gateway_service/routers/pipeline_routes.py`

    ```python
    from uuid import uuid4
    from fastapi import APIRouter, Depends, status, HTTPException
    from dishka.integrations.fastapi import FromDishka
    from huleedu_service_libs.kafka_client import KafkaBus
    from huleedu_service_libs.logging_utils import create_service_logger
    from common_core.events.client_commands import ClientBatchPipelineRequestV1
    from common_core.events.envelope import EventEnvelope
    from ..middleware.rate_limit_middleware import limiter
    from .. import auth

    router = APIRouter()
    logger = create_service_logger("api_gateway.pipeline_routes")

    @router.post("/batches/{batch_id}/pipelines", status_code=status.HTTP_202_ACCEPTED)
    @limiter.limit("10/minute")  # CRITICAL: Rate limiting on write endpoints (Architect Feedback #3)
    async def request_pipeline_execution(
        request: Request,  # Required for rate limiting
        batch_id: str,
        pipeline_request: ClientBatchPipelineRequestV1,
        user_id: str = Depends(auth.get_current_user_id),
        kafka_bus: FromDishka[KafkaBus],
    ):
        """
        Request pipeline execution for a batch with comprehensive validation and security.
        
        CRITICAL: This endpoint implements multiple architect feedback items:
        - Rate limiting (#3)
        - User ID propagation with authentication (#1, #2)
        - Comprehensive logging (#9)
        - Proper error handling
        """
        correlation_id = uuid4()
        
        # CRITICAL: Validate batch_id consistency
        if pipeline_request.batch_id and pipeline_request.batch_id != batch_id:
            logger.warning(
                f"Batch ID mismatch: path='{batch_id}', body='{pipeline_request.batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}'"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch ID in path must match batch ID in request body"
            )

        # Ensure path batch_id takes precedence
        pipeline_request.batch_id = batch_id
        pipeline_request.user_id = user_id  # CRITICAL: Propagate authenticated user_id
        pipeline_request.client_correlation_id = correlation_id

        try:
            envelope = EventEnvelope[ClientBatchPipelineRequestV1](
                event_type="huleedu.commands.batch.pipeline.v1",
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=pipeline_request,
            )

            await kafka_bus.publish(
                topic="huleedu.commands.batch.pipeline.v1",
                envelope=envelope,
                key=batch_id  # Partition by batch_id for ordering
            )

            # CRITICAL: Comprehensive logging for traceability (Architect Feedback #9)
            logger.info(
                f"Pipeline request published: batch_id='{batch_id}', "
                f"pipeline='{pipeline_request.requested_pipeline}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}'"
            )

            return {
                "status": "accepted",
                "message": "Pipeline execution request received",
                "batch_id": batch_id,
                "correlation_id": str(correlation_id)
            }

        except Exception as e:
            logger.error(
                f"Failed to publish pipeline request: batch_id='{batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}', error='{e}'",
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to process pipeline request"
            )
    ```

5. **Assemble the Main Application with Hardening**:

    **File**: `services/api_gateway_service/main.py`

    ```python
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from dishka import make_async_container
    from dishka.integrations.fastapi import setup_dishka
    from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
    
    from .config import settings
    from .di import ApiGatewayProvider
    from .middleware.rate_limit_middleware import limiter, rate_limit_exceeded_handler
    from .routers import pipeline_routes

    # CRITICAL: Configure logging first
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    logger = create_service_logger("api_gateway.main")

    app = FastAPI(
        title="HuleEdu API Gateway",
        description="Secure client-facing API for React frontend",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CRITICAL: Setup DI with graceful shutdown
    container = make_async_container(ApiGatewayProvider())
    setup_dishka(container, app)

    # CRITICAL: Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(429, rate_limit_exceeded_handler)

    # Setup CORS for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Register Routers
    app.include_router(pipeline_routes.router, prefix="/v1", tags=["Pipelines"])

    @app.on_event("startup")
    async def startup():
        """Initialize service with comprehensive logging."""
        logger.info(f"Starting {settings.SERVICE_NAME} on port {settings.HTTP_PORT}")
        logger.info(f"CORS origins: {settings.CORS_ORIGINS}")
        logger.info(f"Rate limiting: {limiter._default_limits}")

    @app.on_event("shutdown") 
    async def shutdown():
        """CRITICAL: Graceful shutdown with proper resource cleanup (Architect Feedback #4)."""
        logger.info("Shutting down API Gateway Service...")
        try:
            await container.close()
            logger.info("API Gateway Service shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
    ```

**Configuration Updates**:

**File**: `services/api_gateway_service/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # CRITICAL: Security configuration
    JWT_SECRET_KEY: str = Field(..., description="JWT signing secret - MUST be in secrets manager")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="JWT token expiry")
    
    # CRITICAL: Timeout configuration (Architect Feedback #6)  
    HTTP_CLIENT_TIMEOUT_SECONDS: int = Field(default=10, description="Total HTTP client timeout")
    HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS: int = Field(default=5, description="HTTP client connect timeout")
    
    # Rate limiting configuration (Architect Feedback #3)
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Rate limit: requests per minute per client")
    REDIS_HOST: str = Field(default="redis", description="Redis host for rate limiting")
    REDIS_PORT: int = Field(default=6379, description="Redis port for rate limiting")
```

**Done When**:

- ✅ JWT validation includes expiry checks and comprehensive error handling (Architect Feedback #2).
- ✅ Rate limiting is implemented on write endpoints to prevent abuse (Architect Feedback #3).
- ✅ HTTP clients have configured timeouts to prevent indefinite hangs (Architect Feedback #6).
- ✅ Graceful shutdown hooks ensure proper resource cleanup during deployments (Architect Feedback #4).
- ✅ Comprehensive logging includes `batch_id`, `user_id`, and `correlation_id` for full traceability (Architect Feedback #9).
- ✅ A `POST` request to `/v1/batches/{batch_id}/pipelines` with valid JWT successfully publishes events with user context.
- ✅ The endpoint returns `202 Accepted` with proper correlation tracking.
- ✅ Requests without valid JWT or with expired tokens are rejected with appropriate HTTP status codes.
- ✅ Rate limiting triggers `429 Too Many Requests` responses when limits are exceeded.

### Checkpoint 2.3: Student Validation Flow Endpoints

**Objective**: Implement API endpoints to support the enhanced student validation workflow, including validation status checking, student association confirmation, and timeout handling.

**Affected Files**:

- `services/api_gateway_service/routers/validation_routes.py` (new)
- `services/api_gateway_service/routers/batch_routes.py` (new)
- `services/api_gateway_service/main.py` (updated)

**Implementation Steps**:

1. **Student Validation Router**: Create endpoints for validation workflow management.

    **File**: `services/api_gateway_service/routers/validation_routes.py`

    ```python
    from typing import List, Dict, Any
    from uuid import uuid4
    from fastapi import APIRouter, Depends, status, HTTPException, Request
    from dishka.integrations.fastapi import FromDishka
    from pydantic import BaseModel, Field
    from huleedu_service_libs.kafka_client import KafkaBus
    from huleedu_service_libs.logging_utils import create_service_logger
    from common_core.events.class_events import StudentAssociationsConfirmedV1
    from common_core.events.envelope import EventEnvelope
    from ..middleware.rate_limit_middleware import limiter
    from .. import auth

    router = APIRouter()
    logger = create_service_logger("api_gateway.validation_routes")

    class StudentAssociationRequest(BaseModel):
        """Request model for student association."""
        essay_id: str = Field(..., description="Essay identifier")
        student_id: str = Field(..., description="Student identifier")

    class BatchValidationRequest(BaseModel):
        """Request model for batch validation confirmation."""
        class_id: str = Field(..., description="Class identifier for validation")
        associations: List[StudentAssociationRequest] = Field(..., description="List of student associations")

    class ValidationStatusResponse(BaseModel):
        """Response model for validation status."""
        batch_id: str
        validation_required: bool
        essays_pending_validation: int
        total_essays: int
        timeout_hours_remaining: float | None = None
        class_type: str
        can_modify_files: bool

    @router.get("/batches/{batch_id}/validation-status", response_model=ValidationStatusResponse)
    @limiter.limit("30/minute")
    async def get_batch_validation_status(
        request: Request,
        batch_id: str,
        user_id: str = Depends(auth.get_current_user_id),
        http_session: FromDishka[aiohttp.ClientSession],
    ):
        """Get current validation status for a batch."""
        try:
            # Query File Service for validation status
            file_service_url = f"{settings.FILE_SERVICE_URL}/batch/{batch_id}/validation-status"
            
            async with http_session.get(file_service_url, headers={"X-User-ID": user_id}) as response:
                if response.status == 404:
                    raise HTTPException(status_code=404, detail="Batch not found")
                elif response.status == 403:
                    raise HTTPException(status_code=403, detail="Access denied")
                elif response.status != 200:
                    raise HTTPException(status_code=503, detail="Service unavailable")
                
                status_data = await response.json()
                
                return ValidationStatusResponse(
                    batch_id=batch_id,
                    validation_required=status_data.get("requires_validation", False),
                    essays_pending_validation=status_data.get("essays_pending", 0),
                    total_essays=status_data.get("total_essays", 0),
                    timeout_hours_remaining=status_data.get("hours_remaining"),
                    class_type=status_data.get("class_type", "REGULAR"),
                    can_modify_files=status_data.get("can_modify", False)
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting validation status for batch {batch_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/batches/{batch_id}/confirm-associations", status_code=status.HTTP_202_ACCEPTED)
    @limiter.limit("5/minute")  # Lower limit for critical operations
    async def confirm_student_associations(
        request: Request,
        batch_id: str,
        validation_request: BatchValidationRequest,
        user_id: str = Depends(auth.get_current_user_id),
        kafka_bus: FromDishka[KafkaBus],
    ):
        """Confirm student associations for a batch."""
        correlation_id = uuid4()
        
        try:
            # Create confirmation event
            associations_data = [
                {"essay_id": assoc.essay_id, "student_id": assoc.student_id}
                for assoc in validation_request.associations
            ]
            
            confirmation_event = StudentAssociationsConfirmedV1(
                batch_id=batch_id,
                user_id=user_id,
                class_id=validation_request.class_id,
                associations=associations_data,
                validation_metadata={
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                    "total_associations": len(associations_data),
                    "confirmation_method": "manual"
                }
            )

            envelope = EventEnvelope[StudentAssociationsConfirmedV1](
                event_type="huleedu.class.student.associations.confirmed.v1",
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=confirmation_event,
            )

            await kafka_bus.publish(
                topic="huleedu.class.student.associations.confirmed.v1",
                envelope=envelope,
                key=batch_id
            )

            logger.info(
                f"Student associations confirmed: batch_id='{batch_id}', "
                f"associations={len(associations_data)}, user_id='{user_id}', "
                f"correlation_id='{correlation_id}'"
            )

            return {
                "status": "accepted",
                "message": "Student associations confirmation received",
                "batch_id": batch_id,
                "associations_count": len(associations_data),
                "correlation_id": str(correlation_id)
            }

        except Exception as e:
            logger.error(
                f"Error confirming associations for batch {batch_id}: {e}",
                exc_info=True
            )
            raise HTTPException(status_code=500, detail="Failed to confirm associations")

    @router.post("/batches/{batch_id}/skip-validation", status_code=status.HTTP_202_ACCEPTED)
    @limiter.limit("3/minute")  # Very low limit for skip operations
    async def skip_batch_validation(
        request: Request,
        batch_id: str,
        user_id: str = Depends(auth.get_current_user_id),
        kafka_bus: FromDishka[KafkaBus],
    ):
        """Skip validation for a batch (use high-confidence matches, unknown for others)."""
        correlation_id = uuid4()
        
        try:
            # Create skip validation event (reuse timeout processing logic)
            skip_event = ValidationTimeoutProcessedV1(
                batch_id=batch_id,
                timeout_hours=0,  # Immediate processing
                auto_assigned_count=0,  # Will be calculated by ELS
                unknown_assigned_count=0  # Will be calculated by ELS
            )

            envelope = EventEnvelope[ValidationTimeoutProcessedV1](
                event_type="huleedu.validation.timeout.processed.v1",
                source_service="api_gateway_service",
                correlation_id=correlation_id,
                data=skip_event,
            )

            await kafka_bus.publish(
                topic="huleedu.validation.timeout.processed.v1",
                envelope=envelope,
                key=batch_id
            )

            logger.info(
                f"Validation skipped: batch_id='{batch_id}', user_id='{user_id}', "
                f"correlation_id='{correlation_id}'"
            )

            return {
                "status": "accepted",
                "message": "Validation skip request received",
                "batch_id": batch_id,
                "correlation_id": str(correlation_id)
            }

        except Exception as e:
            logger.error(f"Error skipping validation for batch {batch_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to skip validation")
    ```

2. **Batch Management Router**: Create endpoints for enhanced batch operations.

    **File**: `services/api_gateway_service/routers/batch_routes.py`

    ```python
    from typing import List, Optional
    from uuid import uuid4
    from fastapi import APIRouter, Depends, status, HTTPException, Request, UploadFile, File
    from dishka.integrations.fastapi import FromDishka
    from pydantic import BaseModel, Field
    from huleedu_service_libs.kafka_client import KafkaBus
    from huleedu_service_libs.logging_utils import create_service_logger
    from common_core.enums import CourseCode
    from ..middleware.rate_limit_middleware import limiter
    from .. import auth

    router = APIRouter()
    logger = create_service_logger("api_gateway.batch_routes")

    class EnhancedBatchRegistrationRequest(BaseModel):
        """Enhanced batch registration request with course and class support."""
        expected_essay_count: int = Field(..., gt=0)
        course_code: CourseCode | None = Field(None, description="Course code (None for GUEST class)")
        class_id: str | None = Field(None, description="Existing class ID")
        class_designation: str = Field(..., description="Class designation or 'GUEST'")
        essay_instructions: str = Field(...)
        enable_student_parsing: bool = Field(default=True)
        validation_timeout_hours: int = Field(default=72, ge=1, le=168)  # 1 hour to 1 week

    class BatchStatusResponse(BaseModel):
        """Response model for batch status."""
        batch_id: str
        status: str
        class_type: str
        validation_required: bool
        can_modify_files: bool
        essays_count: int
        course_info: dict | None = None

    @router.post("/batches/register", status_code=status.HTTP_201_CREATED)
    @limiter.limit("10/minute")
    async def register_enhanced_batch(
        request: Request,
        registration_request: EnhancedBatchRegistrationRequest,
        user_id: str = Depends(auth.get_current_user_id),
        http_session: FromDishka[aiohttp.ClientSession],
    ):
        """Register a new batch with enhanced course and validation support."""
        try:
            # Forward to BOS enhanced registration endpoint
            bos_url = f"{settings.BOS_URL}/v2/register"
            
            registration_data = registration_request.model_dump()
            registration_data["user_id"] = user_id
            
            async with http_session.post(
                bos_url, 
                json=registration_data,
                headers={"X-User-ID": user_id}
            ) as response:
                if response.status == 201:
                    batch_data = await response.json()
                    logger.info(f"Enhanced batch registered: {batch_data.get('batch_id')}, user: {user_id}")
                    return batch_data
                elif response.status == 400:
                    error_data = await response.json()
                    raise HTTPException(status_code=400, detail=error_data.get("error", "Validation error"))
                else:
                    raise HTTPException(status_code=503, detail="Batch registration service unavailable")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering enhanced batch: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to register batch")

    @router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
    @limiter.limit("30/minute")
    async def get_batch_status(
        request: Request,
        batch_id: str,
        user_id: str = Depends(auth.get_current_user_id),
        http_session: FromDishka[aiohttp.ClientSession],
    ):
        """Get enhanced batch status information."""
        try:
            # Query BOS for batch status
            bos_url = f"{settings.BOS_URL}/internal/v1/batches/{batch_id}/status"
            
            async with http_session.get(bos_url, headers={"X-User-ID": user_id}) as response:
                if response.status == 404:
                    raise HTTPException(status_code=404, detail="Batch not found")
                elif response.status == 403:
                    raise HTTPException(status_code=403, detail="Access denied")
                elif response.status != 200:
                    raise HTTPException(status_code=503, detail="Service unavailable")
                
                batch_data = await response.json()
                metadata = batch_data.get("processing_metadata", {})
                
                return BatchStatusResponse(
                    batch_id=batch_id,
                    status=batch_data.get("status", "unknown"),
                    class_type=metadata.get("class_type", "REGULAR"),
                    validation_required=metadata.get("validation_required", False),
                    can_modify_files=batch_data.get("can_modify_files", False),
                    essays_count=batch_data.get("essays_count", 0),
                    course_info={
                        "course_code": metadata.get("course_code"),
                        "language": metadata.get("language"),
                        "course_name": metadata.get("course_name")
                    } if metadata.get("class_type") == "REGULAR" else None
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting batch status {batch_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    ```

3. **Update Main Application**: Register the new routers.

    **File**: `services/api_gateway_service/main.py`

    ```python
    # ... existing imports ...
    from .routers import pipeline_routes, validation_routes, batch_routes

    # ... existing code ...

    # Register Routers
    app.include_router(pipeline_routes.router, prefix="/v1", tags=["Pipelines"])
    app.include_router(validation_routes.router, prefix="/v1", tags=["Validation"])
    app.include_router(batch_routes.router, prefix="/v1", tags=["Batches"])

    # ... rest of existing code ...
    ```

**Done When**:

- ✅ Validation status endpoint provides comprehensive batch validation information
- ✅ Student association confirmation endpoint publishes validation events
- ✅ Validation skip endpoint allows teachers to bypass validation when needed
- ✅ Enhanced batch registration supports GUEST class and validation timeout configuration
- ✅ Batch status endpoint provides enhanced information including validation state
- ✅ All endpoints include proper authentication, rate limiting, and error handling

This completes Part 2 of the implementation guide. The API Gateway is now capable of receiving and processing commands. Part 3 will focus on implementing the query and real-time WebSocket components.
