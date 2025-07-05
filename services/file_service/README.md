# HuleEdu File Service

The File Service is a microservice responsible for handling file uploads, text extraction, content validation, and content provisioning within the HuleEdu platform. It serves as the entry point for batch file processing workflows.

## Purpose & Workflow

The File Service implements a robust content ingestion and validation workflow:

1. **Pre-emptive Raw Storage**: Upon receiving a file, its raw, unmodified content is immediately stored in the Content Service. This creates an immutable source of truth and returns a `raw_file_storage_id`.
2. **Text Extraction**: The service extracts plaintext from the raw file bytes.
3. **Content Validation**: The extracted text is validated against business rules (e.g., minimum/maximum length).
4. **Conditional Event Publishing**: Based on the validation result, the service publishes one of two events to Kafka to coordinate with the Essay Lifecycle Service (ELS).

## Architecture

The service follows HuleEdu's standard microservice patterns:

- **Blueprint-based API**: Organized route definitions in `api/` directory.
- **Protocol-based DI**: Clean architecture with Dishka dependency injection.
- **Event-driven coordination**: Publishes events to Kafka for ELS.
- **Async operations**: Full async/await implementation.

## API Endpoints

### File Operations

#### `POST /v1/files/batch`

Upload multiple files for batch processing.

**Request:** `multipart/form-data` with `batch_id` and `files` fields.

**Response:** `202 Accepted` with a confirmation message and `correlation_id`.

### Health and Monitoring

#### `GET /healthz`

Service health check endpoint.

#### `GET /metrics`

Prometheus metrics endpoint.

## Configuration

The service uses Pydantic settings with the `FILE_SERVICE_` environment variable prefix. Key settings include Kafka/Content Service URLs and content validation parameters (`MIN_CONTENT_LENGTH`, `MAX_CONTENT_LENGTH`).

## Event Integration

### Published Events

#### `EssayContentProvisionedV1` (on Success)

- **Topic:** `huleedu.file.essay.content.provisioned.v1`
- **Purpose**: Published when a file is successfully validated and its text content is stored.
- **Payload**: Includes `batch_id`, `original_file_name`, `raw_file_storage_id`, and `text_storage_id`.

#### `EssayValidationFailedV1` (on Failure)

- **Topic:** `huleedu.file.essay.validation.failed.v1`
- **Purpose**: Published when a file fails the content validation step. This is critical for ELS to adjust its batch expectations and prevent stalls.
- **Payload**: Includes `batch_id`, `original_file_name`, `raw_file_storage_id` (for traceability), and a specific `validation_error_code`.

## Development

### Local Development

```bash
# Install dependencies
pdm install

# Run development server
pdm run -p services/file_service dev
```

## Docker Development

```bash
# Install dependencies
pdm install
# Build image
docker build -t huleedu-file-service .

# Run container
docker run -p 7001:7001 -p 9094:9094 huleedu-file-service
```

## Circuit Breaker Monitoring

Circuit breaker observability is available through the `/metrics` endpoint:

- **`circuit_breaker_state`**: Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) with labels: `service`, `circuit_name`
- **`circuit_breaker_state_changes`**: State transition counter with labels: `service`, `circuit_name`, `from_state`, `to_state`
- **`circuit_breaker_calls_total`**: Call result counter with labels: `service`, `circuit_name`, `result` (success/failure/blocked)

Circuit breakers protect Kafka publishing operations and are controlled via `FILE_SERVICE_CIRCUIT_BREAKER_` configuration settings.
