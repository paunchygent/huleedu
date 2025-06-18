# API Gateway Service

## Overview **Client-facing API for React frontend integration**

The API Gateway Service is a FastAPI-based microservice that provides client-facing HTTP endpoints for React frontend applications. It serves as the entry point for external clients and publishes commands to internal microservices via Kafka.

## Architecture

- **Framework**: FastAPI + uvicorn (client-facing optimization)
- **Communication**: HTTP API for React frontend, Kafka for internal commands
- **Port**: 4001 (client-facing)
- **Features**: CORS, OpenAPI docs, rate limiting, authentication-ready

## Key Responsibilities

1. **Client API**: HTTP endpoints for React frontend
2. **Command Publishing**: Kafka event publishing to internal services
3. **Request Validation**: Comprehensive input validation and sanitization
4. **Documentation**: Automatic OpenAPI/Swagger documentation
5. **Security**: Rate limiting, CORS, authentication hooks

## API Endpoints

### Client-Facing API

- `POST /v1/batches/{batch_id}/pipelines` - Request pipeline execution
- `GET /v1/batches/{batch_id}/status` - Get batch status
- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## React Frontend Integration

### CORS Configuration

Configured for React development and production environments:

- Development: `http://localhost:3000`, `http://localhost:3001`
- Production: Configurable via environment variables

### Request/Response Format

Optimized for React state management with comprehensive validation and helpful error messages.

### API Documentation

Automatic OpenAPI schema generation for frontend development:

- Interactive documentation at `/docs`
- Alternative documentation at `/redoc`
- JSON schema available at `/openapi.json`

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

### Docker

```bash
# Build image
docker build -t huleedu/api-gateway-service .

# Run container
docker run -p 4001:4001 huleedu/api-gateway-service
```

## Configuration

Environment variables (prefix: `API_GATEWAY_`):

- `API_GATEWAY_HTTP_HOST`: Server host (default: 0.0.0.0)
- `API_GATEWAY_HTTP_PORT`: Server port (default: 4001)
- `API_GATEWAY_LOG_LEVEL`: Logging level (default: INFO)
- `API_GATEWAY_CORS_ORIGINS`: Allowed CORS origins (JSON array)
- `API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers
- `API_GATEWAY_RATE_LIMIT_REQUESTS`: Requests per minute (default: 100)

## Security Features

### Rate Limiting

- Per-client rate limiting (100 requests/minute default)
- Per-endpoint granular limits
- Burst protection

### Authentication (Future)

- JWT middleware hooks ready
- OAuth integration preparation
- Role-based access control framework

### Input Validation

- Strict Pydantic model validation
- SQL injection prevention
- XSS protection in error responses

## Service Integration

**Publishes to**: Kafka (`huleedu.commands.batch.pipeline.v1`)  
**Consumed by**: React Frontend Applications

## Monitoring

- Health checks via `/healthz`
- Prometheus metrics via `/metrics`
- Request/response logging with correlation IDs
- Performance metrics (request duration, error rates)

## Testing

### FastAPI TestClient

Comprehensive testing with FastAPI's built-in test client:

```python
from fastapi.testclient import TestClient
from .main import app

client = TestClient(app)
response = client.get("/healthz")
```

### CORS Testing

Validation of CORS configuration with React development server.

---

**Status**: Phase 1 - Architectural Foundation Complete  
**Next Phase**: Phase 3 - API Gateway Implementation 