# Implementation Guide: HuleEdu Client Interface Layer (2/3)

This document provides a step-by-step implementation plan for the API Gateway component of the client interface layer.

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

### Checkpoint 2.2: Implement Authentication & Command Endpoint

**Objective**: Secure the gateway and implement the primary endpoint for initiating backend workflows.

**Affected Files**:

- `services/api_gateway_service/auth.py` (new)
- `services/api_gateway_service/routers/pipeline_routes.py` (new)
- `services/api_gateway_service/main.py` (new)
- `services/api_gateway_service/di.py` (new)

**Implementation Steps**:

1. **Create Authentication Dependency**: This reusable component will validate JWTs.

    **File**: `services/api_gateway_service/auth.py`

    ```python
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer
    import jwt
    from .config import settings

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token") # Placeholder

    async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id: str | None = payload.get("sub") # 'sub' is standard for subject/user_id
            if user_id is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            return user_id
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    ```

2. **Implement DI Providers**: Set up the Dishka provider to supply dependencies like `KafkaBus` and `aiohttp.ClientSession`.

    **File**: `services/api_gateway_service/di.py`

    ```python
    from aiohttp import ClientSession
    from dishka import Provider, Scope, provide
    from huleedu_service_libs.kafka_client import KafkaBus
    from .config import settings

    class ApiGatewayProvider(Provider):
        @provide(scope=Scope.APP)
        async def provide_kafka_bus(self) -> KafkaBus:
            bus = KafkaBus(client_id=settings.SERVICE_NAME, bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
            await bus.start()
            return bus

        @provide(scope=Scope.APP)
        async def provide_http_session(self) -> ClientSession:
            return ClientSession()
    ```

3. **Implement the Command Endpoint Router**:

    **File**: `services/api_gateway_service/routers/pipeline_routes.py`

    ```python
    from uuid import uuid4
    from fastapi import APIRouter, Depends, status
    from dishka.integrations.fastapi import FromDishka
    from huleedu_service_libs.kafka_client import KafkaBus
    from common_core.events.client_commands import ClientBatchPipelineRequestV1
    from common_core.events.envelope import EventEnvelope
    from .. import auth

    router = APIRouter()

    @router.post("/batches/{batch_id}/pipelines", status_code=status.HTTP_202_ACCEPTED)
    async def request_pipeline_execution(
        batch_id: str,
        pipeline_request: ClientBatchPipelineRequestV1, # FastAPI validates request body against this
        user_id: str = Depends(auth.get_current_user_id),
        kafka_bus: FromDishka[KafkaBus],
    ):
        correlation_id = uuid4()

        # Ensure the request batch_id matches the path batch_id
        pipeline_request.batch_id = batch_id

        pipeline_request.user_id = user_id # Propagate the authenticated user_id


        envelope = EventEnvelope[ClientBatchPipelineRequestV1](
            event_type="huleedu.commands.batch.pipeline.v1",
            source_service="api_gateway_service",
            correlation_id=correlation_id,
            data=pipeline_request,
        )

        await kafka_bus.publish(
            topic="huleedu.commands.batch.pipeline.v1",
            envelope=envelope,
            key=batch_id # Partition by batch_id
        )

        return {"status": "accepted", "batch_id": batch_id, "correlation_id": str(correlation_id)}
    ```

4. **Assemble the Main Application**:

    **File**: `services/api_gateway_service/main.py`

    ```python
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from dishka import make_async_container
    from dishka.integrations.fastapi import setup_dishka
    from .config import settings
    from .di import ApiGatewayProvider
    from .routers import pipeline_routes #, status_routes, websocket_routes

    app = FastAPI(title="HuleEdu API Gateway")

    # Setup DI
    container = make_async_container(ApiGatewayProvider())
    setup_dishka(container, app)

    # Setup Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Routers
    app.include_router(pipeline_routes.router, prefix="/v1", tags=["Pipelines"])
    # app.include_router(status_routes.router, prefix="/v1", tags=["Status"])
    # app.include_router(websocket_routes.router, tags=["Real-time"])
    ```

**Integration Points**:

- **Publishes To**: Kafka topic `huleedu.commands.batch.pipeline.v1`.
- **Consumed By**: The `batch_orchestrator_service`'s `ClientPipelineRequestHandler`.

**Done When**:

- ✅ A request to `POST /v1/batches/{batch_id}/pipelines` with a valid JWT and Pydantic body successfully publishes a `ClientBatchPipelineRequestV1` event to Kafka.
- ✅ The endpoint returns a `202 Accepted` response with a valid `correlation_id`.
- ✅ Requests without a valid JWT are rejected with a `401 Unauthorized`.
- ✅ Requests with an invalid request body are rejected with a `422 Unprocessable Entity`.

This completes Part 2 of the implementation guide. The API Gateway is now capable of receiving and processing commands. Part 3 will focus on implementing the query and real-time WebSocket components.
