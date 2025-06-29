# API Gateway Service

## Overview **Client-facing API for React frontend integration**

The API Gateway Service is a FastAPI-based microservice that provides client-facing HTTP endpoints for React frontend applications. It serves as the secure entry point for external clients, implementing authentication, rate limiting, and proper request validation while proxying to internal microservices.

## Architecture

- **Framework**: FastAPI + uvicorn (client-facing optimization)
- **Communication**: HTTP API for React frontend, Kafka for batch commands, HTTP proxy for file uploads
- **Port**: 4001 (client-facing)
- **Features**: CORS, OpenAPI docs, rate limiting, JWT authentication, WebSocket support, Anti-Corruption Layer

## Key Responsibilities

1. **Client API**: Secure HTTP endpoints for React frontend
2. **Batch Commands**: Kafka event publishing using proper `ClientBatchPipelineRequestV1` contracts
3. **File Upload Proxy**: Secure file upload proxy to File Service with authentication headers
4. **Real-time Updates**: WebSocket connections for live batch status updates
5. **Class Management Proxy**: Complete proxy to Class Management Service API
6. **Security**: Authentication, rate limiting, CORS, input validation
7. **Anti-Corruption Layer**: Transforms internal backend schemas to stable client contracts

## API Endpoints

### Batch Management

- `POST /v1/batches/{batch_id}/pipelines` - Request pipeline execution (uses `ClientBatchPipelineRequestV1`)
- `GET /v1/batches/{batch_id}/status` - Get batch status with ownership validation and ACL transformation
- `GET /v1/batches/{batch_id}/validation-status` - Get validation status for student associations

### File Operations  

- `POST /v1/files/batch` - Upload files to batch (proxy to File Service)

### Class Management (Proxy)

- `ANY /v1/classes/{path:path}` - Complete proxy to Class Management Service API
  - Supports all HTTP methods (GET, POST, PUT, DELETE)
  - Headers and query parameters are forwarded
  - Authentication headers are passed through

### Real-time Communication

- `WebSocket /ws/v1/status/{client_id}` - Real-time batch status updates (requires JWT token in query parameter)

### Service Management

- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics  
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Security Features

### JWT Authentication

- All endpoints require valid JWT tokens
- User ownership validation for batch operations
- Secure WebSocket authentication via query parameters

### Rate Limiting

- Batch commands: 10 requests/minute
- File uploads: 5 requests/minute  
- Status queries: 50 requests/minute
- Per-client enforcement with Redis backend

### Request Validation

- Strict Pydantic model validation using `common_core` contracts
- Batch ID consistency validation (path vs. body)
- Comprehensive error handling with detailed logging

## Data Contracts

Uses proper shared contracts from `common_core`:

- **Pipeline Commands**: `ClientBatchPipelineRequestV1` with user context and retry support
- **Event Publishing**: `EventEnvelope` format to `huleedu.commands.batch.pipeline.v1` topic
- **Validation**: Student association handling for class-based batches
- **ACL Transformation**: Converts BOS `ProcessingPipelineState` to RAS `BatchStatusResponse` during fallback

## React Frontend Integration

### CORS Configuration

- Development: `http://localhost:3000`, `http://localhost:3001`
- Production: Configurable via `API_GATEWAY_CORS_ORIGINS`

### WebSocket Integration

```javascript
const ws = new WebSocket(`ws://localhost:4001/ws?token=${jwtToken}`);
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  // Handle batch_phase_concluded, file_added, etc.
};
```

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
pdm run lint
pdm run format
```

### Testing

Comprehensive test suite with:

- Contract validation tests for `ClientBatchPipelineRequestV1`
- File upload proxy tests with mocked File Service
- Authentication and rate limiting tests
- Error handling and edge case validation

## Configuration

Environment variables (prefix: `API_GATEWAY_`):

- `API_GATEWAY_SERVICE_NAME`: Service identifier (default: api-gateway-service)
- `API_GATEWAY_HTTP_HOST`: Server host (default: 0.0.0.0)  
- `API_GATEWAY_HTTP_PORT`: Server port (default: 4001)
- `API_GATEWAY_LOG_LEVEL`: Logging level (default: INFO)
- `API_GATEWAY_CORS_ORIGINS`: Allowed CORS origins (JSON array)
- `API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: kafka:9092)
- `API_GATEWAY_FILE_SERVICE_URL`: File Service URL (default: http://file_service:8000)
- `API_GATEWAY_CMS_API_URL`: Class Management Service URL (default: http://class_management_service:8000)
- `API_GATEWAY_REDIS_URL`: Redis URL for rate limiting (default: redis://redis:6379)
- `API_GATEWAY_JWT_SECRET_KEY`: JWT signing secret (REQUIRED)

## Service Integration

**Publishes to**:

- Kafka topic: `huleedu.commands.batch.pipeline.v1` (batch pipeline commands)

**Proxies to**:

- File Service: `/v1/files/batch` (file uploads)
- Class Management Service: `/v1/classes/*` (all class operations)

**Real-time**:

- Redis Pub/Sub: User-specific channels for WebSocket updates

**Consumed by**: React Frontend Applications

## Monitoring

- Health checks via `/healthz`
- Prometheus metrics via `/metrics`
- Comprehensive logging with correlation IDs
- User action traceability for security auditing

---

**Status**: ✅ **IMPLEMENTATION COMPLETE**  
**Features**: Batch commands, file uploads, class management proxy, WebSocket support, comprehensive testing
