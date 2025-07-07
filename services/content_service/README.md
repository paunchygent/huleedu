# HuleEdu Content Service

## 🎯 Overview and Purpose

The **Content Service** is a foundational utility microservice within the HuleEdu platform. Its singular and clearly defined responsibility is to provide a centralized, reliable, and straightforward mechanism for **storing and retrieving raw digital content (blobs)**.

Other services within the HuleEdu ecosystem, such as the Spell Checker Service and Batch Orchestrator Service, depend on the Content Service for persisting and accessing immutable content objects, like original essay texts or their processed versions. The Content Service itself does not interpret the business meaning of the content it stores; it treats them as opaque data blobs referenced by a unique `storage_id`.

While future enhancements include metadata tracking, this will focus on metadata directly pertaining to the content objects managed by this service (e.g., technical details like MIME type, size, versioning, and basic descriptive tags). More complex, business-specific metadata, state tracking, or aggregated views of content are the responsibility of other services like the Essay Lifecycle Service or a planned Result Aggregator service.

## Key Responsibilities

* **Content Persistence**: Securely stores raw binary data and provides a unique `storage_id` for later retrieval.
* **Content Retrieval**: Serves the raw binary data associated with a given `storage_id`.
* **Simplicity**: Offers a minimal and focused API for these core storage operations.

## Architecture and Technologies

* **Service Type**: Asynchronous HTTP API service.
* **Framework**: Built with Quart, a Python ASGI web framework.
* **ASGI Server**: Served by Hypercorn. Configuration for Hypercorn is in `hypercorn_config.py`.
* **File Operations**: Uses the `aiofiles` library for non-blocking, asynchronous file system interactions.
* **Storage Backend**:
  * Currently utilizes the local filesystem.
  * Content files are named using UUIDs (without file extensions).
* **Dependency Injection**: Includes `dishka` as a dependency. Protocol definitions like `ContentRepositoryProtocol` are in `protocols.py`.

## 🚀 API Endpoints

The service API is versioned under `/v1`:

* **`POST /v1/content`**
  * **Description**: Stores raw binary data.
  * **Request Body**: Raw binary data.
  * **Success Response (201)**: JSON `{"storage_id": "generated-uuid"}`.
  * **Error Responses**: `400` (no data), `500` (storage error).

* **`GET /v1/content/<string:content_id>`**
  * **Description**: Retrieves content using its `storage_id`.
  * **Success Response (200)**: The raw content data.
  * **Error Responses**: `400` (invalid ID), `404` (not found), `500` (retrieval error).

* **`GET /healthz`**
  * **Description**: Health check endpoint.
  * **Success Response (200)**: JSON `{"status": "ok", "message": "Content Service is healthy."}`.
  * **Error Response (503)**: If storage is not accessible or other health issues.

* **`GET /metrics`**
  * **Description**: Prometheus metrics endpoint.
  * **Success Response (200)**: Metrics in OpenMetrics format.

## ⚙️ Configuration

Configuration is managed via `services/content_service/config.py` using Pydantic's `BaseSettings`.
Environment variables are prefixed with `CONTENT_SERVICE_`.

Key settings include:

* `CONTENT_SERVICE_LOG_LEVEL`: Logging verbosity (Default: "INFO").
* `CONTENT_SERVICE_CONTENT_STORE_ROOT_PATH`: Root directory for content files. (Default: `./.local_content_store_mvp` for local, `/data/huleedu_content_store` in Docker).
* `CONTENT_SERVICE_PORT`: Service listening port.

An example environment file is available at `services/content_service/.env.example`.

## 🧱 Dependencies

### Libraries

Key Python libraries are listed in `services/content_service/pyproject.toml`:

* `quart`, `aiofiles`, `hypercorn`
* `python-dotenv`, `pydantic`, `pydantic-settings`
* `huleedu-common-core`, `huleedu-service-libs`
* `prometheus-client`, `dishka`

### Infrastructure

* Within Docker Compose, it depends on `kafka_topic_setup` completing, ensuring the broader system's Kafka infrastructure is ready.

## 💻 Local Development

1. **Prerequisites**: Python 3.11+, PDM.
2. **Install Dependencies**: From monorepo root: `pdm install -G dev`.
3. **Environment**: Create and configure `.env` in `services/content_service/` from `.env.example`.
4. **Run**: From monorepo root: `pdm run dev-content`.

## 🧪 Testing

Service-specific tests (assumed to be in `services/content_service/tests/`) can be run using:

```bash
# From the monorepo root
pdm run pytest services/content_service/tests/ -v
```

## 📊 Technical Patterns

### Health Check Implementation

The service implements a **simple, dependency-aware health check** pattern without database requirements:

```python
# From api/health_routes.py
@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Standardized health check endpoint with storage validation."""
    checks = {"service_responsive": True, "dependencies_available": True}
    dependencies = {}
    
    # Storage accessibility check
    store_path = settings.CONTENT_STORE_ROOT_PATH
    if not store_path.exists() or not store_path.is_dir():
        dependencies["storage"] = {
            "status": "unhealthy",
            "error": f"Storage path {store_path.resolve()} not accessible",
        }
        checks["dependencies_available"] = False
    else:
        dependencies["storage"] = {
            "status": "healthy",
            "path": str(store_path.resolve()),
            "writable": True,
        }
```

### Storage Strategy

The service employs a **flat file storage pattern** with UUID-based naming:

```python
# From implementations/filesystem_content_store.py
async def save_content(self, content_data: bytes) -> str:
    """UUID-based flat file storage without directory hierarchy."""
    content_id = uuid.uuid4().hex  # 32-character hex string
    file_path = self.store_root / content_id  # Direct storage, no subdirs
    
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content_data)
    
    return content_id
```

**Key characteristics:**
- No file extensions (treats all content as opaque blobs)
- No directory hierarchy (all files in single root directory)
- UUID hex format validation in retrieval endpoint
- Async I/O for non-blocking operations

### Performance Metrics

The service tracks operations using **Prometheus counters with dimensional labels**:

```python
# From di.py - Metrics initialization
content_operations = Counter(
    "content_operations_total",
    "Total content operations",
    ["operation", "status"],  # Dimensional tracking
    registry=registry,
)

# From implementations/prometheus_content_metrics.py
def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
    self.content_operations.labels(
        operation=operation.value,  # UPLOAD, DOWNLOAD
        status=status.value        # SUCCESS, FAILED, ERROR, NOT_FOUND
    ).inc()
```

**Additional HTTP metrics:**
```python
# From startup_setup.py
"http_requests_total": Counter(..., ["method", "endpoint", "status_code"]),
"http_request_duration_seconds": Histogram(..., ["method", "endpoint"]),
```

### Error Recovery Patterns

The service implements **defensive error handling** with appropriate status codes:

```python
# From api/content_routes.py - Upload error handling
try:
    raw_data = await request.data
    if not raw_data:
        metrics.record_operation(OperationType.UPLOAD, OperationStatus.FAILED)
        return jsonify({"error": "No data provided"}), 400
    
    content_id = await store.save_content(raw_data)
    metrics.record_operation(OperationType.UPLOAD, OperationStatus.SUCCESS)
    return jsonify({"storage_id": content_id}), 201
except Exception as e:
    logger.error(f"Error during content upload: {e}", exc_info=True)
    metrics.record_operation(OperationType.UPLOAD, OperationStatus.ERROR)
    return jsonify({"error": "Failed to store content."}), 500
```

**Validation patterns:**
- Content ID format validation (32 hex chars)
- Empty upload rejection (400 Bad Request)
- File existence check before serving (404 Not Found)
- Generic error response for unexpected failures (500)

### Scaling Considerations

#### File System Limits

**Current limitations:**
- **Flat directory structure**: Performance degrades with >10K files per directory
- **No content deduplication**: Identical content creates duplicate files
- **No file size limits**: Large uploads could exhaust disk space

**Mitigation strategies:**
```python
# Future enhancement: Hierarchical storage
# Example: ab/cd/ef/abcdef... (3-level hierarchy)
content_id = uuid.uuid4().hex
file_path = self.store_root / content_id[:2] / content_id[2:4] / content_id[4:6] / content_id
```

#### Concurrent Operation Handling

The service leverages **async/await patterns** for concurrent request handling:

```python
# Non-blocking file operations with aiofiles
async with aiofiles.open(file_path, "wb") as f:
    await f.write(content_data)

# Async file existence check
return bool(await aiofiles.os.path.isfile(str(file_path)))
```

**Concurrency characteristics:**
- Each request gets its own coroutine
- File I/O doesn't block the event loop
- No explicit locking (relies on filesystem atomicity)

#### Caching Strategies

**Current state**: No caching implemented

**Potential enhancements:**
```python
# In-memory LRU cache for frequently accessed content
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_cached_content_path(self, content_id: str) -> Path:
    return self.store_root / content_id

# HTTP caching headers for client-side caching
response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
response.headers['ETag'] = f'"{content_id}"'