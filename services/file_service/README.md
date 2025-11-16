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
- **Event-driven coordination**: Publishes events directly to Kafka with **Transactional Outbox Pattern as fallback**.
- **Reliable Event Publishing**: TRUE Outbox Pattern - all events stored in outbox database first, then published by relay worker.
- **Event Relay Worker**: Redis-driven background worker with instant wake-up for zero-delay processing.
- **Async operations**: Full async/await implementation.

## API Endpoints

### File Operations

#### `POST /v1/files/batch`

Upload multiple files for batch processing.

**Request:** `multipart/form-data` with `batch_id` and `files` fields.

**Response:** `202 Accepted` with a confirmation message and `correlation_id`.

**Upstream Identity (via API Gateway):**

- Headers forwarded by API Gateway include:
  - `X-User-ID` (always)
  - `X-Correlation-ID` (always)
  - `X-Org-ID` (optional, present when client JWT contains an organization identity)

### Health and Monitoring

#### `GET /healthz`

Service health check endpoint.

#### `GET /metrics`

Prometheus metrics endpoint.

## Configuration

The service uses Pydantic settings with the `FILE_SERVICE_` environment variable prefix. Key settings include Kafka/Content Service URLs and content validation parameters (`MIN_CONTENT_LENGTH`, `MAX_CONTENT_LENGTH`).

## Event Integration

All events are published using a **TRUE Outbox Pattern** where events are stored in the outbox database table first, then asynchronously published to Kafka by a dedicated relay worker for transactional safety.

### Published Events

#### `EssayContentProvisionedV1` (on Success)

- **Topic:** `huleedu.file.essay.content.provisioned.v1`
- **Purpose**: Published when a file is successfully validated and its text content is stored.
- **Payload**: Includes `batch_id`, `original_file_name`, `raw_file_storage_id`, and `text_storage_id`.
- **Delivery**: TRUE Outbox Pattern - stored in database first, published by relay worker.

#### `EssayValidationFailedV1` (on Failure)

- **Topic:** `huleedu.file.essay.validation.failed.v1`
- **Purpose**: Published when a file fails the content validation step. This is critical for ELS to adjust its batch expectations and prevent stalls.
- **Payload**: Includes `batch_id`, `original_file_name`, `raw_file_storage_id` (for traceability), and a specific `validation_error_code`.
- **Delivery**: Direct Kafka publishing; outbox ensures delivery even during Kafka outages.

#### `BatchFileAddedV1` / `BatchFileRemovedV1`

- **Purpose**: File management events for batch coordination.
- **Dual Publishing**: Direct Kafka publish + immediate Redis notification for real-time UI updates.
- **Resilience**: Outbox ensures Kafka delivery; Redis failures don't affect core functionality.

## Development

### Local Development

```bash
# Install dependencies
pdm install

# Run development server
pdm run -p services/file_service dev
```

### Running Tests

```bash
# Run all File Service tests
pdm run pytest services/file_service/ -v

# Run with coverage
pdm run pytest services/file_service/ --cov=services/file_service --cov-report=term-missing

# Run specific test types
pdm run pytest services/file_service/tests/unit/ -v          # Unit tests only
pdm run pytest services/file_service/tests/integration/ -v  # Integration tests

# Run strategy pattern tests specifically
pdm run pytest services/file_service/tests/unit/test_extraction_strategies.py -v
pdm run pytest services/file_service/tests/integration/test_strategy_based_extractor_integration.py -v
```

**Test Coverage:** Maintains >90% coverage including comprehensive Strategy pattern testing.

### Docker Development

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

### 1. Text Extraction Architecture

The service uses a **Strategy Pattern** for extensible text extraction:

```python
# Base strategy protocol
class ExtractionStrategy(Protocol):
    async def extract_text(self, file_content: bytes, correlation_id: UUID) -> str:
        """Extract text from file content with correlation tracking."""
        ...

# Individual strategy implementations
class TxtExtractionStrategy(ExtractionStrategy):
    async def extract_text(self, file_content: bytes, correlation_id: UUID) -> str:
        return file_content.decode("utf-8", errors="ignore")

class DocxExtractionStrategy(ExtractionStrategy):
    async def extract_text(self, file_content: bytes, correlation_id: UUID) -> str:
        return await asyncio.to_thread(self._extract_docx_sync, file_content)

class PdfExtractionStrategy(ExtractionStrategy):
    async def extract_text(self, file_content: bytes, correlation_id: UUID) -> str:
        return await asyncio.to_thread(self._extract_pdf_sync, file_content)
```

**Strategy Registration:**

```python
# Dependency injection setup
strategies = {
    ".txt": TxtExtractionStrategy(),
    ".docx": DocxExtractionStrategy(), 
    ".pdf": PdfExtractionStrategy()
}
extractor = StrategyBasedTextExtractor(strategies)
```

### 2. Health Check Implementation

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

### 2. Text Extraction Strategy Pattern

The service implements a **Strategy Pattern** for text extraction supporting multiple file formats:

```python
# Strategy-based text extractor with pluggable extraction strategies
class StrategyBasedTextExtractor:
    def __init__(self, strategies: dict[str, ExtractionStrategy]):
        self.strategies = strategies
    
    async def extract_text(
        self, 
        file_content: bytes, 
        file_name: str, 
        correlation_id: UUID
    ) -> str:
        file_extension = Path(file_name).suffix.lower()
        strategy = self.strategies.get(file_extension)
        
        if not strategy:
            raise UnsupportedFileTypeError(f"No strategy for {file_extension}")
        
        return await strategy.extract_text(file_content, correlation_id)
```

**Supported File Types:**

- **`.txt`**: UTF-8 decoding with error handling
- **`.docx`**: Microsoft Word document parsing using python-docx
- **`.pdf`**: PDF text extraction using pypdf with encrypted file detection

**Error Handling:**

- Encrypted PDFs raise `ENCRYPTED_FILE_UNSUPPORTED` structured error
- Corrupted files handled gracefully with specific error codes
- Each strategy implements async extraction with correlation ID tracking

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

### 5. Transactional Outbox Pattern (Kafka-First with Fallback)

**Event Publishing Architecture**:

```python
class DefaultEventPublisher(EventPublisherProtocol):
    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: RedisClientProtocol,
        settings: Settings,
    ):
        self.kafka_bus = kafka_bus
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: UUID,
    ) -> None:
        """Publish event using TRUE Outbox Pattern."""
        envelope = EventEnvelope[EssayContentProvisionedV1](
            event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
        )
        
        try:
            # TRUE OUTBOX PATTERN: All events go to outbox first
            await self.kafka_bus.publish(
                topic=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                key=event_data.file_upload_id.encode("utf-8"),
                value=envelope.model_dump_json(mode="json").encode("utf-8"),
                correlation_id=correlation_id,
            )
            return  # Success - no outbox needed
            
        except Exception as e:
            # FALLBACK: Store in outbox only on Kafka failure
            await self.outbox_repository.add_event(
                aggregate_id=event_data.file_upload_id,
                aggregate_type="file_upload",
                event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                event_data=envelope.model_dump(mode="json"),
                topic=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                event_key=event_data.file_upload_id,
            )
            # Wake up relay worker immediately
            await self.redis_client.lpush("outbox:wakeup", "1")
```

**Database Schema**:

```sql
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    event_data JSONB NOT NULL,
    event_key VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT
);

-- Optimized for relay worker polling
CREATE INDEX ix_event_outbox_unpublished ON event_outbox (published_at, created_at) 
WHERE published_at IS NULL;
```

**Event Relay Worker (Redis-Driven)**:

- **Primary Mode**: Waits on Redis BLPOP for instant wake-up when events enter outbox
- **Adaptive Polling**: 0.1s → 1s → 5s intervals when idle (configured by ENVIRONMENT)
- **Zero-Delay**: Processes events immediately upon Redis notification
- **Centralized Config**: All timing/intervals configured in huleedu_service_libs

### 6. Performance Optimization

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
    ),
    # Outbox pattern metrics
    "outbox_queue_depth_total": Gauge(
        "file_service_outbox_queue_depth_total",
        "Number of unpublished events in outbox"
    ),
    "outbox_events_published_total": Counter(
        "file_service_outbox_events_published_total",
        "Total events successfully published from outbox",
        ["event_type"]
    )
}
```

**Async I/O patterns:**

- All file operations use async/await
- HTTP client session reused via DI (`Scope.APP`)
- No blocking I/O in request handlers
- Event Relay Worker runs as background task
- Outbox repository uses connection pooling for optimal performance

## Error Handling

Uses `libs/huleedu_service_libs/error_handling` for structured error responses with service-specific error codes.

### ErrorCode Usage

- **Service-Specific**: `FileValidationErrorCode` enum for file processing errors:
  - `ENCRYPTED_FILE_UNSUPPORTED` - Encrypted PDF files
  - `CORRUPTED_FILE` - Malformed or corrupted files
  - `EMPTY_CONTENT` - Whitespace-only or empty extracted text
  - `CONTENT_TOO_SHORT` - Below MIN_CONTENT_LENGTH (50 chars)
  - `CONTENT_TOO_LONG` - Above MAX_CONTENT_LENGTH (50,000 chars)
  - `UNSUPPORTED_FILE_TYPE` - File extension not supported (.txt, .docx, .pdf only)

- **Base ErrorCode**: Used for generic errors:
  - `VALIDATION_ERROR` - Invalid request format
  - `EXTERNAL_SERVICE_ERROR` - Content Service failures
  - `PROCESSING_ERROR` - Extraction failures

### Error Propagation

- **HTTP Endpoints**: Raise `HuleEduError` with correlation_id and error code
- **Event Publishing**: Validation failures publish `EssayValidationFailedV1` with error code
- **Transactional Outbox**: Ensures failure events delivered reliably
- **Strategy Pattern**: Each extraction strategy handles format-specific errors

### Error Response Structure

All errors follow standard structure:

```python
from huleedu_service_libs.error_handling import HuleEduError
from services.file_service.error_codes import FileValidationErrorCode

# Validation failure
raise HuleEduError(
    error_code=FileValidationErrorCode.EMPTY_CONTENT,
    message="Extracted text is empty or whitespace-only",
    correlation_id=correlation_id
)

# Unsupported file type
raise HuleEduError(
    error_code=FileValidationErrorCode.UNSUPPORTED_FILE_TYPE,
    message=f"No extraction strategy for {file_extension}",
    correlation_id=correlation_id
)
```

Event failure publishing:

```python
failure_event = EssayValidationFailedV1(
    batch_id=batch_id,
    original_file_name=file_name,
    raw_file_storage_id=raw_storage_id,
    validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
    correlation_id=correlation_id
)
```

Reference: `libs/common_core/docs/error-patterns.md`

## Testing

### Test Structure

```
tests/
├── unit/                          # Unit tests with mocked dependencies
│   ├── test_extraction_strategies.py
│   ├── test_core_logic_*.py
│   ├── test_content_validator.py
│   ├── test_file_validators.py
│   ├── test_event_relay_worker.py
│   ├── test_outbox_manager_error_handling.py
│   └── ...
├── integration/                   # Integration tests with testcontainers
│   ├── test_strategy_based_extractor_integration.py
│   ├── test_outbox_pattern_integration.py
│   ├── test_outbox_repository.py
│   └── conftest.py
└── conftest.py                   # Shared fixtures
```

### Running Tests

```bash
# All tests
pdm run pytest-root services/file_service/tests/ -v

# Unit tests only
pdm run pytest-root services/file_service/tests/unit/ -v

# Integration tests (requires testcontainers)
pdm run pytest-root services/file_service/tests/integration/ -v -m integration

# Strategy pattern tests specifically
pdm run pytest-root services/file_service/tests/unit/test_extraction_strategies.py -v
pdm run pytest-root services/file_service/tests/integration/test_strategy_based_extractor_integration.py -v

# With coverage
pdm run pytest-root services/file_service/tests/ --cov=services/file_service --cov-report=term-missing
```

### Common Test Markers

- `@pytest.mark.asyncio` - Async unit tests
- `@pytest.mark.integration` - Integration tests requiring external dependencies

### Test Patterns

- **Protocol-based mocking**: Use `AsyncMock(spec=ProtocolName)` for dependencies
- **Strategy pattern testing**: Mock individual extraction strategies
- **Testcontainers**: PostgreSQL containers for outbox integration tests
- **Correlation tracking**: Verify correlation_id propagation through workflows
- **Error scenarios**: Test all FileValidationErrorCode cases
- **Transactional outbox**: Verify event persistence and relay worker behavior

### Critical Test Scenarios

- **File type support**: .txt, .docx, .pdf extraction strategies
- **Validation boundaries**: MIN_CONTENT_LENGTH, MAX_CONTENT_LENGTH
- **Encrypted PDFs**: ENCRYPTED_FILE_UNSUPPORTED error handling
- **Empty files**: EMPTY_CONTENT error handling
- **Corrupted files**: CORRUPTED_FILE error handling
- **Content Service failures**: Retry and error handling
- **Transactional outbox**: Event persistence and publishing
- **Event Relay Worker**: Instant wake-up and batch publishing

**Test Coverage**: >90% maintained across unit and integration tests

Reference: `.claude/rules/075-test-creation-methodology.mdc`

## Migration Workflow

### Creating Migrations

From service directory:

```bash
cd services/file_service/

# Generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Review generated migration in alembic/versions/
# Edit if needed (constraints, indexes, data migrations)

# Apply migration
alembic upgrade head
```

### Migration Standards

- **Naming**: `YYYYMMDD_HHMM_short_description.py`
- **File Service tables**: file_uploads (user-facing file management)
- **Outbox alignment**: Use shared `EventOutbox` model from `huleedu_service_libs.outbox.models`
- **Indexes**: Add indexes for query patterns (batch_id, user_id, upload_timestamp)
- **Verification**: Run `alembic history --verbose` after creating migrations

### Existing Migrations

- `20250725_0001_add_event_outbox_table.py` - Transactional outbox pattern
- `20250807_0036_f3ce45362241_add_file_uploads_table_for_user_.py` - User-facing file tracking
- `20250808_1151_4073c6627a50_add_explicit_topic_column_to_event_.py` - Outbox improvement

### Critical Notes

- File Service owns file_uploads table (user-facing file management)
- Outbox table owned by shared library
- No essay_states table (owned by Essay Lifecycle Service)
- Never modify pushed migrations - create new migration to fix issues
- Test migrations against testcontainer database before pushing

Reference: `.claude/rules/085-database-migration-standards.md`
