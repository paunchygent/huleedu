# API Gateway Service

## Overview **Client-facing API for Svelte 5 + Vite frontend integration**

The API Gateway Service is a FastAPI-based microservice that provides client-facing HTTP endpoints for Svelte 5 + Vite frontend applications. It serves as the secure entry point for external clients, implementing authentication, rate limiting, and proper request validation while proxying to internal microservices.

## Architecture

- **Framework**: FastAPI + uvicorn (client-facing optimization)
- **Communication**: HTTP API for Svelte 5 + Vite frontend, Kafka for batch commands, HTTP proxy for file uploads
- **Port**: 4001 (client-facing)
- **Features**: CORS, OpenAPI docs, rate limiting, JWT authentication

## Key Responsibilities

1. **Client API**: Secure HTTP endpoints for Svelte 5 + Vite frontend
2. **Batch Commands**: Kafka event publishing using proper `ClientBatchPipelineRequestV1` contracts
3. **File Upload Proxy**: Secure file upload proxy to File Service with authentication headers
4. **Class Management Proxy**: Complete proxy to Class Management Service API
5. **Security**: Authentication, rate limiting, CORS, input validation

## API Endpoints

### Batch Management

- `POST /v1/batches/register` - Register a new batch (proxy to BOS; injects user_id/org_id from JWT)
- `POST /v1/batches/{batch_id}/pipelines` - Request pipeline execution (uses `ClientBatchPipelineRequestV1`)
- `GET /v1/batches/{batch_id}/status` - Get batch status with semantic status mapping and ownership validation
- `GET /v1/batches/{batch_id}/validation-status` - Get validation status for student associations

### File Operations  

- `POST /v1/files/batch` - Upload files to batch (proxy to File Service)

### Class Management (Proxy)

- `ANY /v1/classes/{path:path}` - Complete proxy to Class Management Service API
  - Supports all HTTP methods (GET, POST, PUT, DELETE)
  - Headers and query parameters are forwarded
  - Authentication headers are passed through

### Service Management

- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics  
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Security Features

### JWT Authentication

- All endpoints require valid JWT tokens
- User ownership validation for batch operations

### Rate Limiting

- Batch commands: 20 requests/minute
- File uploads: 50 requests/minute  
- Status queries: 50 requests/minute (lightweight)
- Per-user enforcement with Redis backend; falls back to IP when unauthenticated

### Architecture Decision: DI Bridge for Rate Limiting

- We use a thin AuthBridge middleware to decode JWT once and expose `user_id`/`org_id` on `request.state` so SlowAPI (middleware-first) can key limits per user.
- The route-level AuthProvider reuses the same decoded payload (no double decode) and remains the single source of truth for authentication errors.
- This cleanly adapts Dishka DI to middleware expectations without duplicating auth logic.

### Request Validation

- Strict Pydantic model validation using `common_core` contracts
- Batch ID consistency validation (path vs. body)
- Comprehensive error handling with detailed logging

## Data Contracts

Uses proper shared contracts from `common_core`:

- **Pipeline Commands**: `ClientBatchPipelineRequestV1` with user context and retry support
- **Event Publishing**: `EventEnvelope` format to `huleedu.commands.batch.pipeline.v1` topic
- **Validation**: Student association handling for class-based batches

## Status Mapping System

### Client-Facing Status Values

The API Gateway maps internal processing states to semantic client statuses for consistent frontend integration:

- `pending_content` - Batch created, awaiting content validation or pipeline configuration
- `ready` - Files uploaded and validated, ready for processing  
- `processing` - Currently being processed through pipeline phases
- `completed_successfully` - All essays processed successfully
- `completed_with_failures` - Processing completed but some essays failed
- `failed` - Processing failed with critical errors
- `cancelled` - Processing cancelled by user or system

### REST/WebSocket Consistency

Status values returned by `/v1/batches/{batch_id}/status` are **identical** to WebSocket notification values, ensuring frontend applications receive consistent status information regardless of communication channel.

## Svelte Frontend Integration

### CORS Configuration

- Development: `http://localhost:3000`, `http://localhost:3001`
- Production: Configurable via `API_GATEWAY_CORS_ORIGINS`

### File Upload

```javascript
const formData = new FormData();
formData.append('files', file1);
formData.append('files', file2);
formData.append('batch_id', batchId);

fetch('/v1/files/batch', {
  method: 'POST',
  body: formData,
  headers: { 'Authorization': `Bearer ${token}` }
});
```

## Development

### Requirements

- Python 3.11+
- PDM for dependency management
- Docker for containerization

### Local Development

```bash
# Install dependencies
pdm install

# Run service locally
pdm run dev

# Run tests
pdm run test

# Lint and format
pdm run format-all
pdm run lint-fix --unsafe-fixes
```

### Testing

Comprehensive test suite with:

- Contract validation tests for `ClientBatchPipelineRequestV1`
- File upload proxy tests with mocked File Service
- Authentication and rate limiting tests
- Error handling and edge case validation

## Error Handling

Uses `libs/huleedu_service_libs/error_handling` for structured error responses.

### ErrorCode Usage

- **Base ErrorCode**: Service uses base `ErrorCode` from `common_core.error_enums`:
  - `VALIDATION_ERROR` - Invalid request data, batch ID mismatch
  - `AUTHENTICATION_ERROR` - Invalid JWT token, missing credentials
  - `RESOURCE_NOT_FOUND` - Batch not found
  - `EXTERNAL_SERVICE_ERROR` - File Service, BOS, CMS proxy failures
  - `RATE_LIMIT` - Rate limit exceeded

- No service-specific ErrorCode enum (uses base errors only)

### Error Propagation

- **HTTP Endpoints**: FastAPI exception handlers convert `HuleEduError` to HTTP responses
- **Proxy Routes**: Preserve upstream error responses from File Service, BOS, CMS
- **JWT Validation**: Authentication failures return 401 with correlation_id
- **Rate Limiting**: SlowAPI middleware returns 429 with rate limit headers

### Error Response Structure

All errors follow standard structure:

```python
from huleedu_service_libs.error_handling import HuleEduError
from common_core.error_enums import ErrorCode

raise HuleEduError(
    error_code=ErrorCode.VALIDATION_ERROR,
    message="Batch ID in path must match batch_id in request body",
    correlation_id=correlation_context.uuid
)
```

FastAPI response format:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Batch ID in path must match batch_id in request body",
  "correlation_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

Reference: `libs/common_core/docs/error-patterns.md`

## Testing

### Test Structure

```
tests/
├── test_auth.py                      # JWT authentication tests
├── test_auth_org.py                  # Org-level authentication tests
├── test_batch_routes.py              # Batch pipeline command tests
├── test_batch_registration_proxy.py  # BOS proxy tests
├── test_batch_preflight.py           # Validation status tests
├── test_status_routes.py             # Status mapping tests
├── test_file_routes.py               # File upload proxy tests
├── test_class_routes.py              # Class Management proxy tests
├── test_health_routes.py             # Health check tests
├── test_provider.py                  # DI provider tests
└── conftest.py                       # Shared fixtures
```

### Running Tests

```bash
# All tests
pdm run pytest-root services/api_gateway_service/tests/ -v

# Specific test files
pdm run pytest-root services/api_gateway_service/tests/test_auth.py -v
pdm run pytest-root services/api_gateway_service/tests/test_batch_routes.py -v
```

### Common Test Markers

- `@pytest.mark.asyncio` - Async tests
- `@pytest.mark.unit` - Unit tests with mocked dependencies
- `@pytest.mark.integration` - Integration tests requiring Redis, Kafka

### Test Patterns

- **FastAPI test client**: Use `httpx.AsyncClient` with app
- **JWT fixtures**: Mock JWT tokens in conftest.py
- **Service mocking**: Mock File Service, BOS, CMS HTTP responses
- **Rate limit testing**: Mock Redis backend for SlowAPI
- **Correlation context**: Test correlation_id propagation through requests

Reference: `.claude/rules/075-test-creation-methodology.md`

## Configuration

Environment variables (prefix: `API_GATEWAY_`):

- `API_GATEWAY_SERVICE_NAME`: Service identifier (default: api-gateway-service)
- `API_GATEWAY_HTTP_HOST`: Server host (default: 0.0.0.0)
- `API_GATEWAY_HTTP_PORT`: Server port (default: 4001)
- `API_GATEWAY_LOG_LEVEL`: Logging level (default: INFO)
- `API_GATEWAY_CORS_ORIGINS`: Allowed CORS origins (JSON array)
- `API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: kafka:9092)
- `API_GATEWAY_FILE_SERVICE_URL`: File Service URL (default: http://file_service:7001)
- `API_GATEWAY_CMS_API_URL`: Class Management Service URL (default: http://class_management_service:5002)
- `API_GATEWAY_BOS_URL`: Batch Orchestrator Service URL (internal-only; default: http://batch_orchestrator_service:5000)
- `API_GATEWAY_REDIS_URL`: Redis URL for rate limiting (default: redis://redis:6379)
- `API_GATEWAY_JWT_SECRET_KEY`: JWT signing secret (REQUIRED)
- `API_GATEWAY_JWT_AUDIENCE`: Expected JWT audience (default: huleedu-platform)
- `API_GATEWAY_JWT_ISSUER`: Expected JWT issuer (default: huleedu-identity-service)

## Service Integration

**Publishes to**:

- Kafka topic: `huleedu.commands.batch.pipeline.v1` (batch pipeline commands)

**Proxies to**:

- File Service: `/v1/files/batch` (file uploads)
- Class Management Service: `/v1/classes/*` (all class operations)
- Batch Orchestrator Service: `/v1/batches/register` (registration proxy)

**Consumed by**: Svelte 5 + Vite Frontend Applications

## Monitoring

- Health checks via `/healthz`
- Prometheus metrics via `/metrics`
- Comprehensive logging with correlation IDs
- User action traceability for security auditing

---

**Status**: ✅ **IMPLEMENTATION COMPLETE**  
**Features**: Batch commands, file uploads, class management proxy, comprehensive testing
