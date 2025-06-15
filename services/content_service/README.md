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