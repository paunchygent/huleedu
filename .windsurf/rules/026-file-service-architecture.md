---
description: Defines the architecture and implementation details of the HuleEdu File Service
globs: 
alwaysApply: false
---
# 026: File Service Architecture

## 1. Service Identity

- **Package**: `huleedu-file-service`
- **Port**: `7001` (HTTP API), `9094` (Prometheus)
- **Stack**: Quart, Hypercorn, aiokafka, aiohttp, Dishka
- **Purpose**: File upload, text extraction, content validation, and event-driven content provisioning service.

## 2. Service Structure & Architecture

- **Blueprint Pattern**: Follows the mandatory Blueprint architecture with a lean `app.py` and routes defined in the `api/` directory.
- **Clean DI**: Uses Dishka for dependency injection with protocols defined in `protocols.py` and implementations in `implementations/`.

```text
services/file_service/
├── app.py                  # Lean Quart application setup
├── startup_setup.py        # DI and metrics initialization
├── api/                    # **REQUIRED**: Blueprint routes
│   ├── health_routes.py    # Standard health and metrics endpoints
│   └── file_routes.py      # /v1/files/batch endpoint
├── implementations/        # Protocol implementations
├── protocols.py            # Service behavioral contracts
├── di.py                   # Dishka dependency injection providers
├── core_logic.py           # Core file processing workflow
└── config.py               # Pydantic settings configuration
```

## 3. API Specification

### POST /v1/files/batch

- **Description**: Accepts multipart form data for batch file uploads.
- **Request**: `multipart/form-data` with `batch_id` and `files[]` fields.
- **Response**: `202 Accepted` with a confirmation message and `correlation_id`.
- **Processing**: Concurrently processes each file using `asyncio.create_task`.

## 4. Processing Implementation

The core workflow in `core_logic.py` follows a robust validation and storage pattern:

1. **Pre-emptive Raw Storage**: The raw, unmodified file content is immediately stored in the Content Service. This establishes an immutable source of truth and returns a `raw_file_storage_id`.
2. **Text Extraction**: Text is extracted from the raw file content.
3. **Content Validation**: The extracted text is validated against business rules (e.g., min/max length) using the `ContentValidatorProtocol`.
4. **Conditional Event Publishing**:
    - If validation **succeeds**, the extracted plaintext is stored in the Content Service (getting a `text_storage_id`), and an `EssayContentProvisionedV1` event is published.
    - If validation **fails**, an `EssayValidationFailedV1` event is published. This event is critical for ELS/BOS coordination, allowing them to adjust batch expectations.

## 5. Event Integration

### 5.1. Published Events

- **Topic**: `huleedu.file.essay.content.provisioned.v1`
  - **Event**: `EssayContentProvisionedV1`
  - **Payload MUST include**: `batch_id`, `original_file_name`, `raw_file_storage_id`, `text_storage_id`, `content_md5_hash`.
- **Topic**: `huleedu.file.essay.validation.failed.v1`
  - **Event**: `EssayValidationFailedV1`
  - **Payload MUST include**: `batch_id`, `original_file_name`, `raw_file_storage_id`, and a specific `validation_error_code` from the `FileValidationErrorCode` enum.

## 6. Configuration

- **Environment Prefix**: `FILE_SERVICE_`
- **Key Settings**:
  - `CONTENT_VALIDATION_ENABLED`: Toggles the validation step.
  - `MIN_CONTENT_LENGTH`, `MAX_CONTENT_LENGTH`: Parameters for the `ContentValidatorProtocol`.

## 7. Protocol Abstractions

The service's dependencies are defined by these protocols in `protocols.py`:

- `ContentServiceClientProtocol`: For storing content.
- `EventPublisherProtocol`: For publishing Kafka events.
- `TextExtractorProtocol`: For extracting text from files.
- `ContentValidatorProtocol`: For validating extracted content.

## 8. Deployment

- **Dockerfile**: `services/file_service/Dockerfile` follows the standard pattern with `PYTHONPATH=/app`.
- **Health Check**: `GET /healthz` is configured in `docker-compose.yml`.

## 9. Mandatory Production Patterns

- **MUST** implement graceful shutdown (`startup_setup.py`).
- **MUST** use DI-managed resources (`KafkaBus`, `ClientSession`).
- **MUST** implement standard health and metrics endpoints via Blueprints.
