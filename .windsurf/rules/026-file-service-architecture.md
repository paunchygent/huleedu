---
description: Defines the architecture and implementation details of the HuleEdu File Service
globs: 
alwaysApply: false
---
# 026: File Service Architecture

## 1. Service Identity
- **Package**: `huleedu-file-service`
- **Port**: 7001 (HTTP API), 9094 (Prometheus)
- **Stack**: Quart, aiohttp, Hypercorn, aiokafka
- **Purpose**: File upload and content provisioning service
- **Architecture**: Blueprint-based API with Kafka event publishing

## 2. Service Structure **BLUEPRINT PATTERN**

### 2.1. Directory Structure
```
services/file_service/
├── app.py                     # Lean Quart application (setup, DI, Blueprint registration)
├── api/                       # Blueprint API routes directory
│   ├── __init__.py
│   ├── health_routes.py       # /healthz, /metrics endpoints
│   └── file_routes.py         # /v1/files endpoints
├── config.py                  # Pydantic settings
├── protocols.py               # Service behavioral contracts
├── di.py                      # Dishka dependency injection providers
├── core_logic.py              # File processing workflow logic
├── text_processing.py         # Text extraction and student info parsing
├── hypercorn_config.py        # Hypercorn server configuration
├── pyproject.toml
├── Dockerfile
├── README.md
└── tests/
```

### 2.2. Blueprint Implementation
- **app.py**: Lean setup focused on Blueprint registration and dependency injection
- **api/health_routes.py**: Standard health and metrics endpoints
- **api/file_routes.py**: File upload and batch processing endpoints
- **Dependencies**: Injected via Dishka with protocol-based abstractions

## 3. API Specification

### 3.1. Endpoints

#### POST /v1/files/batch
- Batch file upload for essay processing
- **Request**: Multipart form with `batch_id` and `files[]`
- **Response**: `{"message": "...", "batch_id": "...", "correlation_id": "..."}`
- **Status**: 202 (accepted), 400 (validation error), 500 (processing error)
- **Processing**: Concurrent file processing with asyncio.create_task
- **Blueprint**: file_routes.py

#### GET /healthz
- Health check endpoint
- **Response**: `{"status": "ok", "message": "File Service is healthy"}`
- **Status**: 200 (healthy), 503 (unhealthy)
- **Blueprint**: health_routes.py

#### GET /metrics
- Prometheus metrics endpoint
- **Response**: Metrics in Prometheus format
- **Status**: 200 (success), 500 (error)
- **Blueprint**: health_routes.py

## 4. Processing Implementation

### 4.1. Text Processing
- **Text Extraction**: UTF-8 decoding for .txt files (walking skeleton)
- **Student Info Parsing**: Stubbed implementation returning (None, None)
- **File Validation**: Warning logs for non-.txt files
- **Error Handling**: Empty string return for unsupported formats

### 4.2. Workflow Logic (core_logic.py)
- **Content Storage**: Integration with Content Service via HTTP (returns `text_storage_id`)
- **Content Integrity**: MD5 hash calculation and file size tracking
- **Event Publishing**: `EssayContentProvisionedV1` events to Kafka
- **Correlation Tracking**: End-to-end traceability

## 5. Integration Points

### 5.1. Dependencies
- **Content Service**: HTTP POST for content storage
- **Kafka**: Event publishing for EssayContentReady events
- **Prometheus**: Metrics collection and exposure

### 5.2. Event Publishing
- **Topic**: `huleedu.file.essay.content.provisioned.v1`
- **Event Type**: `EssayContentProvisionedV1` from `common_core.events.file_events`
- **Data**: `batch_id`, `original_file_name`, `text_storage_id`, `file_size_bytes`, `content_md5_hash`
- **Serialization**: `json.dumps(envelope.model_dump(mode="json"))` for UUID handling

## 6. Configuration

### 6.1. Environment Variables
- `FILE_SERVICE_HTTP_PORT`: HTTP server port (default: 7001)
- `FILE_SERVICE_PROMETHEUS_PORT`: Metrics port (default: 9094)
- `FILE_SERVICE_KAFKA_BOOTSTRAP_SERVERS`: Kafka connection string
- `FILE_SERVICE_CONTENT_SERVICE_URL`: Content Service endpoint
- `FILE_SERVICE_LOG_LEVEL`: Logging level (default: INFO)
- `ENV_TYPE`: Environment type (development, docker, etc.)

### 6.2. Dependencies
- `quart`: Async web framework
- `hypercorn`: ASGI server
- `aiokafka`: Kafka client for event publishing
- `aiohttp`: HTTP client for Content Service integration
- `dishka`, `quart-dishka`: Dependency injection
- `huleedu-common-core`: Shared models and events
- `huleedu-service-libs`: Logging utilities

## 7. Protocol Abstractions

### 7.1. Defined Protocols
- **ContentServiceClientProtocol**: Content storage operations
- **EventPublisherProtocol**: Kafka event publishing
- **TextExtractorProtocol**: File text extraction

### 7.2. Implementation Classes
- **DefaultContentServiceClient**: HTTP-based content storage
- **DefaultEventPublisher**: Kafka event publishing with EventEnvelope
- **DefaultTextExtractor**: Basic .txt file processing

## 8. Deployment

### 8.1. Docker Configuration
- **Base Image**: `python:3.11-slim`
- **Package Manager**: PDM
- **Dependencies**: Content Service, Kafka
- **Health Check**: `/healthz` endpoint
- **Port Exposure**: 7001 (HTTP), 9094 (Prometheus)

### 8.2. Development Commands
- `pdm run start`: Production server with Hypercorn
- `pdm run dev`: Development server with debug mode (port 7001)

## 9. Monitoring and Logging

### 9.1. Logging
- **Utility**: `huleedu_service_libs.logging_utils` (centralized)
- **Levels**: INFO for operations, WARNING for non-txt files, ERROR for failures
- **Correlation IDs**: Tracked throughout file processing workflow
- **Context**: File names, batch IDs, essay IDs, processing stages

### 9.2. Metrics
- **Request Counts**: HTTP requests by method, endpoint, status
- **Request Duration**: Response time measurements
- **File Processing**: Upload counts, processing success/failure rates
- **Endpoint**: `/metrics` (Prometheus format)

## 10. Security Considerations

### 10.1. Current Implementation
- No authentication (internal service)
- No file size limits (walking skeleton)
- No content scanning
- Non-root user in container

### 10.2. Future Enhancements
- File size and type validation
- Virus scanning integration
- Authentication for external access
- Rate limiting

## 11. Limitations and Future Work

### 11.1. Current Limitations (Walking Skeleton)
- .txt files only
- No student info extraction (stubbed)
- No file size limits
- No content validation
- Basic error handling

### 11.2. Planned Enhancements
- Multiple file format support (.doc, .docx, .pdf)
- Student name/email regex extraction
- File size and batch limits
- Enhanced error handling with retries
- Content validation and scanning

## 12. Critical Implementation Notes

### 12.1. UUID Serialization
- **CRITICAL**: Must use `json.dumps(envelope.model_dump(mode="json"))` for Kafka events
- **REASON**: UUID objects are not JSON serializable without mode="json"

### 12.2. File Reading
- **CRITICAL**: Quart file storage uses synchronous `.read()` method
- **PATTERN**: `file_content = file_storage.read()` (NOT await)

### 12.3. Port Management
- **CRITICAL**: Ensure unique port allocation in docker-compose.yml
- **CURRENT**: HTTP=7001, Prometheus=9094 (avoid Kafka's 9092)
