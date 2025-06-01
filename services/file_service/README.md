# HuleEdu File Service

The File Service is a microservice responsible for handling file uploads, text extraction, and content provisioning within the HuleEdu platform. It serves as the entry point for batch file processing workflows.

## Purpose

The File Service implements the content provisioning component of the essay ID coordination architecture, providing:

- HTTP API for batch file uploads
- Text extraction from uploaded files (.txt files in walking skeleton)
- Content storage coordination via Content Service
- Content provisioning event publishing to Essay Lifecycle Service

## Architecture

The service follows HuleEdu's standard microservice patterns:

- **Blueprint-based API**: Organized route definitions in `api/` directory
- **Protocol-based DI**: Clean architecture with Dishka dependency injection
- **Event-driven coordination**: Publishes `EssayContentProvisionedV1` events to Kafka
- **Async operations**: Full async/await implementation

## API Endpoints

### File Operations

#### `POST /v1/files/batch`

Upload multiple files for batch processing.

**Request:**

- Content-Type: `multipart/form-data`
- Form fields:
  - `batch_id`: Batch identifier (required)
  - `files`: Multiple file uploads (required)

**Response:**

- Status: `202 Accepted`
- Body: JSON with processing confirmation and correlation ID

**Example:**

```bash
curl -X POST http://localhost:7001/v1/files/batch \
  -F "batch_id=batch-123" \
  -F "files=@essay1.txt" \
  -F "files=@essay2.txt"
```

### Health and Monitoring

#### `GET /healthz`

Service health check endpoint.

**Response:**

- Status: `200 OK`
- Body: `{"status": "ok", "message": "File Service is healthy"}`

#### `GET /metrics`

Prometheus metrics endpoint.

**Response:**

- Status: `200 OK`
- Content-Type: `text/plain; version=0.0.4; charset=utf-8`
- Body: Prometheus metrics in OpenMetrics format

## Configuration

The service uses Pydantic settings with environment variable support:

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_SERVICE_LOG_LEVEL` | `INFO` | Logging level |
| `FILE_SERVICE_HTTP_PORT` | `7001` | HTTP API port |
| `FILE_SERVICE_PROMETHEUS_PORT` | `9092` | Metrics port |
| `FILE_SERVICE_HOST` | `0.0.0.0` | Bind host |
| `FILE_SERVICE_KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka brokers |
| `FILE_SERVICE_CONTENT_SERVICE_URL` | `http://content_service:8001/v1/content` | Content Service API |

## Event Integration

### Published Events

#### `EssayContentProvisionedV1`

Published when individual essay content is successfully processed and stored.

**Topic:** `huleedu.file.essay.content.provisioned.v1`

**Payload:**

- `batch_id`: Batch this content belongs to
- `original_file_name`: Original uploaded file name
- `text_storage_id`: Content Service storage ID for extracted text
- `file_size_bytes`: Size of processed file in bytes
- `content_md5_hash`: MD5 hash of file content for integrity validation
- `correlation_id`: Request correlation ID for traceability

## Development

### Local Development

```bash
# Install dependencies
pdm install

# Run development server
pdm run dev

# Run with custom port
FILE_SERVICE_HTTP_PORT=8001 pdm run dev
```

### Docker Development

```bash
# Build image
docker build -t huleedu-file-service .

# Run container
docker run -p 7001:7001 -p 9092:9092 huleedu-file-service
```

### Testing

The service integrates with the HuleEdu test suite:

```bash
# Run all tests from project root
pdm run test-all

# Run service-specific tests (when implemented)
pdm run -p services/file_service test
```

## Walking Skeleton Limitations

This implementation is part of the batch coordination walking skeleton with intentional limitations:

- **Text Extraction**: Only supports `.txt` files
- **Student Parsing**: Stubbed to return `None, None`
- **Error Handling**: Basic error logging and response codes
- **File Validation**: Minimal file type checking

These limitations will be addressed in future development phases.

## Integration Points

### Content Service

- **Protocol**: HTTP REST API
- **Endpoint**: `POST /v1/content`
- **Purpose**: Store extracted text content

### Essay Lifecycle Service

- **Protocol**: Kafka events
- **Topic**: `huleedu.file.essay.content.provisioned.v1`
- **Purpose**: Notify of content provisioning for slot assignment

### Batch Orchestrator Service

- **Integration**: Indirect via ELS slot assignment
- **Flow**: BOS generates slots → File Service provisions content → ELS assigns slots → BOS receives readiness

## Monitoring

The service provides comprehensive observability:

- **Structured Logging**: JSON logs with correlation ID tracking
- **Prometheus Metrics**: Request counts, durations, and business metrics
- **Health Checks**: Kubernetes-ready health endpoint
- **Error Tracking**: Detailed error logging with context

## Security Considerations

Current implementation (walking skeleton):

- No authentication (internal service)
- No file content validation
- No size limits
- Non-root container user

Production considerations for future phases:

- File type validation and sanitization
- Content size limits
- Access control integration
- Virus scanning integration
