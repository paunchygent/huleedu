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

## Technical Patterns

### 1. Health Check Implementation

Simple health check pattern with dependency status reporting:

```python
@health_bp.route("/healthz")
async def health_check():
    checks = {"service_responsive": True, "dependencies_available": True}
    dependencies = {
        "storage": {
            "status": "healthy",
            "note": "Storage availability checked during file operations"
        }
    }
    return jsonify({
        "service": "file_service",
        "status": "healthy",
        "version": "1.0.0",
        "checks": checks,
        "dependencies": dependencies,
        "environment": "development"
    }), 200
```

**Metrics endpoint** provides Prometheus metrics via injected `CollectorRegistry`.

### 2. File Type Validation

Current implementation supports `.txt` files only (walking skeleton):

```python
async def extract_text_from_file(file_content: bytes, file_name: str) -> str:
    if not file_name.lower().endswith(".txt"):
        logger.warning(f"Non-txt file received: {file_name}. Walking skeleton only supports .txt files.")
        return ""
    
    text = file_content.decode("utf-8", errors="ignore")
    return text
```

**Validation constraints:**
- `MIN_CONTENT_LENGTH`: 50 characters (configurable)
- `MAX_CONTENT_LENGTH`: 50,000 characters (configurable)
- Empty/whitespace-only content rejected with `EMPTY_CONTENT` error code

### 3. Storage Patterns

**Pre-emptive raw storage** workflow ensures data integrity:

```python
# Step 1: Store raw file immediately (immutable source of truth)
raw_file_storage_id = await content_client.store_content(
    file_content, 
    ContentType.RAW_UPLOAD_BLOB
)

# Step 2-3: Extract and validate text
text = await text_extractor.extract_text(file_content, file_name)
validation_result = await content_validator.validate_content(text, file_name)

# Step 4: Store validated plaintext if validation passes
if validation_result.is_valid:
    text_storage_id = await content_client.store_content(
        text.encode("utf-8"),
        ContentType.EXTRACTED_PLAINTEXT
    )
```

**Async HTTP operations** for Content Service storage:

```python
async with self.http_session.post(
    self.settings.CONTENT_SERVICE_URL,
    data=content_bytes,  # Raw bytes in request body
) as response:
    if response.status == 201:
        result = await response.json()
        return result.get("storage_id")
```

### 4. Error Handling

**Specific error types** with clear failure points:

```python
class FileValidationErrorCode(str, Enum):
    # Technical failures
    RAW_STORAGE_FAILED = "RAW_STORAGE_FAILED"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    
    # Business rule failures
    EMPTY_CONTENT = "EMPTY_CONTENT"
    CONTENT_TOO_SHORT = "CONTENT_TOO_SHORT"
    CONTENT_TOO_LONG = "CONTENT_TOO_LONG"
```

**Validation error format:**

```python
class ValidationResult(BaseModel):
    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None  # User-friendly message
    warnings: list[str] = []
```

**Recovery pattern** - Always publish failure events for downstream coordination:

```python
# Even if raw storage fails, publish event (with special marker)
if storage_failed:
    event = EssayValidationFailedV1(
        raw_file_storage_id="STORAGE_FAILED",  # Special marker
        validation_error_code=FileValidationErrorCode.RAW_STORAGE_FAILED,
        # ... other fields
    )
    await event_publisher.publish_essay_validation_failed(event, correlation_id)
```

### 5. Performance Optimization

**Concurrent file processing** with task management:

```python
# Create concurrent tasks for each file
tasks = []
for file_storage in uploaded_files:
    task = asyncio.create_task(
        process_single_file_upload(
            batch_id=batch_id,
            file_content=file_storage.read(),
            file_name=file_storage.filename,
            # ... dependencies
        )
    )
    tasks.append(task)

# Non-blocking error handling
def _handle_task_result(task: asyncio.Task):
    if task.exception():
        logger.error(f"Error processing file: {task.exception()}")
        
for task in tasks:
    task.add_done_callback(_handle_task_result)
```

**Performance metrics** for monitoring:

```python
METRICS = {
    "files_uploaded_total": Counter(
        "file_service_files_uploaded_total",
        "Total files received by the File Service",
        ["file_type", "validation_status", "batch_id"]
    ),
    "text_extraction_duration_seconds": Histogram(
        "file_service_text_extraction_duration_seconds",
        "Time spent extracting text from files"
    ),
    "content_validation_duration_seconds": Histogram(
        "file_service_content_validation_duration_seconds",
        "Time spent validating extracted content"
    )
}
```

**Async I/O patterns:**
- All file operations use async/await
- HTTP client session reused via DI (`Scope.APP`)
- No blocking I/O in request handlers
