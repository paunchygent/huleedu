# BFF Teacher Service

Backend-for-Frontend aggregation layer for the Teacher Dashboard.

## Overview

| Attribute | Value |
|-----------|-------|
| **Port** | 4101 |
| **Framework** | FastAPI |
| **Role** | Aggregates data from RAS and CMS for teacher-facing screens |
| **Pattern** | BFF (Backend-for-Frontend) per ADR-0007 |

This service sits between the API Gateway and internal backend services, providing screen-optimized responses for the Vue 3 Teacher Dashboard frontend.

## Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   API Gateway   │────▶│  BFF Teacher Service │────▶│      RAS        │
│   (JWT Auth)    │     │     (Aggregation)    │     │ (Batch Data)    │
└─────────────────┘     └─────────────────────┘     └─────────────────┘
                                  │
                                  ▼
                        ┌─────────────────┐
                        │       CMS       │
                        │  (Class Info)   │
                        └─────────────────┘
```

### Directory Structure

```
services/bff_teacher_service/
├── api/
│   ├── v1/
│   │   ├── __init__.py          # Router aggregation
│   │   └── teacher_routes.py    # Dashboard endpoint
│   ├── health_routes.py         # Health checks
│   └── spa_routes.py            # Vue SPA fallback
├── clients/
│   ├── _utils.py                # Auth header builder
│   ├── ras_client.py            # RAS HTTP client
│   └── cms_client.py            # CMS HTTP client
├── dto/
│   └── teacher_v1.py            # Response DTOs
├── tests/
│   ├── unit/                    # Unit tests (35 tests)
│   └── test_provider.py         # DI test providers
├── app.py                       # FastAPI application
├── config.py                    # Settings
├── di.py                        # Dishka DI providers
├── middleware.py                # CorrelationID middleware
└── protocols.py                 # Client protocols
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/bff/v1/teacher/dashboard` | Teacher dashboard data |

### GET /bff/v1/teacher/dashboard

Aggregates batch data from RAS with class information from CMS.

**Query Parameters:**

| Param | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `limit` | int | 20 | 1-100 | Maximum batches to return |
| `offset` | int | 0 | >= 0 | Number of batches to skip |
| `status` | string | null | See below | Filter by client status |

**Valid status values:**
- `pending_content` - Awaiting content validation
- `ready` - Ready for pipeline execution
- `processing` - Pipelines in progress
- `completed_successfully` - All essays processed
- `completed_with_failures` - Completed with some failures
- `failed` - Critical failure
- `cancelled` - Batch cancelled

**Response:**

```json
{
  "batches": [
    {
      "batch_id": "uuid-string",
      "title": "Hamlet Essay Analysis",
      "class_name": "Class 9A",
      "status": "processing",
      "total_essays": 25,
      "completed_essays": 18,
      "created_at": "2025-12-10T12:00:00Z"
    }
  ],
  "total_count": 1,
  "limit": 20,
  "offset": 0
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid status filter (VALIDATION_ERROR)
- `401` - Missing X-User-ID header (AUTHENTICATION_ERROR)
- `502` - Backend service error (EXTERNAL_SERVICE_ERROR)

## Authentication

All `/bff/v1/*` endpoints require the `X-User-ID` header, which is injected by the API Gateway from the JWT token. Requests without this header return 401.

```
X-User-ID: <user-uuid>
X-Correlation-ID: <correlation-uuid>  # Optional, auto-generated if missing
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BFF_TEACHER_SERVICE_PORT` | 4101 | HTTP server port |
| `BFF_TEACHER_SERVICE_RAS_URL` | `http://result_aggregator_service:4003` | RAS base URL |
| `BFF_TEACHER_SERVICE_CMS_URL` | `http://class_management_service:5002` | CMS base URL |
| `HULEEDU_INTERNAL_API_KEY` | - | Internal service authentication key |
| `BFF_TEACHER_SERVICE_SERVICE_ID` | `bff_teacher_service` | Service identifier for internal auth |

## Service Dependencies

### Result Aggregator Service (RAS)

**Endpoint:** `GET /internal/v1/batches/user/{user_id}`

Provides batch summaries with pagination. BFF maps internal statuses to client-friendly values.

**Internal Status Mapping:**

| Internal Status | Client Status |
|-----------------|---------------|
| `awaiting_content_validation` | `pending_content` |
| `awaiting_pipeline_configuration` | `pending_content` |
| `ready_for_pipeline_execution` | `ready` |
| `processing_pipelines` | `processing` |
| `awaiting_student_validation` | `processing` |
| `student_validation_completed` | `processing` |
| `validation_timeout_processed` | `processing` |
| `completed_successfully` | `completed_successfully` |
| `completed_with_failures` | `completed_with_failures` |
| `content_ingestion_failed` | `failed` |
| `failed_critically` | `failed` |
| `cancelled` | `cancelled` |

### Class Management Service (CMS)

**Endpoint:** `GET /internal/v1/batches/class-info?batch_ids=<uuid1>,<uuid2>,...`

Returns class information for batches. Batches without class associations return `null`.

## Error Handling

Uses centralized error handling from `huleedu_service_libs.error_handling`:

| Scenario | HTTP Status | Error Code |
|----------|-------------|------------|
| Missing X-User-ID header | 401 | `AUTHENTICATION_ERROR` |
| Invalid status filter | 400 | `VALIDATION_ERROR` |
| Backend service timeout | 504 | `TIMEOUT_ERROR` |
| Backend connection failure | 502 | `CONNECTION_ERROR` |
| Backend HTTP error | 502 | `EXTERNAL_SERVICE_ERROR` |

Error response format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid status filter. Must be one of: cancelled, completed_successfully, ...",
    "correlation_id": "uuid-string",
    "service": "bff_teacher_service",
    "operation": "get_teacher_dashboard"
  }
}
```

## Dependency Injection

Uses Dishka for DI with protocol-based abstractions:

**Protocols** (`protocols.py`):
- `RASClientProtocol` - RAS HTTP client interface
- `CMSClientProtocol` - CMS HTTP client interface

**Providers** (`di.py`):
- `BFFTeacherProvider` - Infrastructure (httpx client, service clients)
- `RequestContextProvider` - Request-scoped (user_id, correlation_id)

**Test Providers** (`tests/test_provider.py`):
- `InfrastructureTestProvider` - Mock httpx client
- `AuthTestProvider` - Fixed user_id for testing

## Development

### Prerequisites

- Docker running (for dependent services)
- `.env` configured with `HULEEDU_INTERNAL_API_KEY`

### Running Locally

```bash
# Start all dependencies
pdm run dev-start

# Or start just the BFF service
pdm run dev-start bff_teacher_service

# Health check
curl http://localhost:4101/healthz

# Dashboard (requires X-User-ID)
curl -H "X-User-ID: test-user" http://localhost:4101/bff/v1/teacher/dashboard
```

### PDM Scripts

```bash
pdm run bff-build          # Build Docker image
pdm run bff-start          # Start service
pdm run bff-logs           # View logs
pdm run bff-restart        # Restart service
```

## Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_teacher_routes.py      # 8 tests - core functionality
│   ├── test_dashboard_edge_cases.py # 17 tests - pagination, status filter
│   ├── test_ras_client.py          # 5 tests - RAS client
│   └── test_cms_client.py          # 5 tests - CMS client
└── test_provider.py                # DI test providers
```

### Running Tests

```bash
# All BFF tests
pdm run pytest-root services/bff_teacher_service/tests/ -v

# Unit tests only
pdm run pytest-root services/bff_teacher_service/tests/unit/ -v

# Functional tests (requires Docker)
ALLOW_REAL_LLM_FUNCTIONAL=1 pdm run pytest-root tests/functional/test_bff_teacher_dashboard_functional.py -v
```

### Test Patterns

Tests use `respx` for HTTP mocking and Dishka test providers:

```python
@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id="test-user"),
        FastapiProvider(),
    )
    app = FastAPI()
    # ... setup
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

## TypeScript Types

Generated types for frontend consumption:

**Location:** `docs/reference/apis/bff-teacher-types.ts`

**Regenerate after API changes:**
```bash
pdm run bff-openapi  # Export OpenAPI schema
pdm run bff-types    # Generate TypeScript types
```

## Related Documentation

- **Programme Hub:** `TASKS/programs/teacher_dashboard_integration/HUB.md`
- **Architecture Decision:** `docs/decisions/0007-bff-vs-api-gateway-pattern.md`
- **Frontend Integration:** `frontend/TASKS/integration/bff-service-implementation-plan.md`
- **Error Handling:** `libs/huleedu_service_libs/docs/error-patterns.md`

## Changelog

- **2025-12-10** - Phase 2: Added pagination (limit, offset) and status filtering
- **2025-12-10** - Phase 1: Initial implementation with RAS/CMS clients
- **2025-12-08** - Service scaffolding with Vue 3 static asset serving
