# Batch Orchestrator Service

## Service Purpose and Role

The **Batch Orchestrator Service** (formerly known as Batch Service) is a core component of the HuleEdu microservice ecosystem. It acts as the primary orchestrator for managing batches of essays and initiating their processing workflows through various specialized services.

Its key responsibilities include:

* Accepting requests to process essays (currently individual, with batch processing planned).
* Coordinating with the Content Service to store the initial essay content.
* Publishing events to Kafka to trigger specific processing phases (e.g., spell checking).
* (Planned) Sending commands to the Essay Lifecycle Service (ELS) to manage the state of essays within a batch and initiate different processing phases for entire batches.
* (Planned) Providing API endpoints for creating and monitoring the status of essay batches.

## Architecture Overview

* **Service Type**: Quart-based asynchronous HTTP API service.
* **Primary Communication**: Exposes an HTTP API for clients to submit essays/batches and publishes events to Kafka to initiate downstream processing.
* **Dependency Injection**: Utilizes Dishka for managing dependencies, with protocol-based abstractions. Service providers are defined in `di.py` and protocols in `protocols.py`.
* **Configuration**: Managed via `config.py` using Pydantic `BaseSettings`, loading from environment variables and `.env` files.

## API Endpoints

The service exposes the following HTTP API endpoints. (All endpoints are prefixed with `/v1` as per architectural standards).

### Current Endpoints

* **`POST /v1/trigger-spellcheck`**:
  * Accepts essay text.
  * Stores the content via the Content Service.
  * Publishes a `SpellcheckRequestedDataV1` event to Kafka.
  * Returns a 202 (Accepted) response with an `essay_id` and `correlation_id`.
* **`GET /healthz`**:
  * Standard health check endpoint. Returns `{"status": "ok"}`.

### Planned Endpoints

* `POST /v1/batch`: For creating a new batch of essays.
* `POST /v1/batch/{batch_id}/initiate-spellcheck`: To initiate spellchecking for an entire batch (likely by sending a command to ELS).
* `GET /v1/batch/{batch_id}/status`: To get the processing status of a batch.

## Event Publishing

The service publishes events to Kafka to initiate processing tasks for other services.

* **Event**: `huleedu.essay.spellcheck.requested.v1`
  * **Data Model**: `SpellcheckRequestedDataV1`
  * **Topic**: Dynamically determined by `topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)` from `common_core.enums`.
  * **Trigger**: Typically published after a successful call to the `/v1/trigger-spellcheck` endpoint.

## Commands Sent (Planned)

As a primary orchestrator, this service will issue commands to the Essay Lifecycle Service (ELS) to manage batch processing phases. These commands will use Pydantic models defined in `common_core.batch_service_models` such as:

* `BatchServiceSpellcheckInitiateCommandDataV1`
* `BatchServiceNLPInitiateCommandDataV1`
* `BatchServiceAIFeedbackInitiateCommandDataV1`
* `BatchServiceCJAssessmentInitiateCommandDataV1`

## Configuration

Key environment variables (typically prefixed with `BATCH_ORCHESTRATOR_SERVICE_` if following the Pydantic Settings pattern established in other services):

* `PORT`: The port on which the HTTP server listens (e.g., 5000).
* `HOST`: The host address for the server (e.g., "0.0.0.0").
* `KAFKA_BOOTSTRAP_SERVERS`: Comma-separated list of Kafka bootstrap servers (e.g., "kafka:9092").
* `CONTENT_SERVICE_URL`: The URL for the Content Service API (e.g., "http://content_service:8000/v1/content").
* `LOG_LEVEL`: Logging verbosity (e.g., INFO, DEBUG).

The service uses `config.py` with Pydantic's `BaseSettings` for type-safe configuration management.

## Dependencies

### Internal Services

* **Kafka**: For event publishing.
* **Content Service**: For storing essay content.
* **Essay Lifecycle Service (ELS)**: (Planned deep integration) For receiving batch processing commands.

### Libraries

* `quart`, `hypercorn`: For the asynchronous HTTP API.
* `aiokafka`: For Kafka communication.
* `aiohttp`: For making asynchronous HTTP calls to other services (e.g., Content Service).
* `huleedu-common-core`: For shared Pydantic models and enums.
* `huleedu-service-libs`: For shared utilities like Kafka client wrappers and logging.
* `pydantic`, `pydantic-settings`: For data validation and configuration.
* `dishka`, `quart-dishka`: For dependency injection.
(Based on dependencies in and common patterns across services like ELS)

## Local Development

1. **Prerequisites**:
    * Ensure Kafka and Content Service are running (e.g., via `pdm run docker-up` from the monorepo root).
    * Python 3.11+ and PDM.

2. **Environment Configuration**:
    Create a `.env` file in the `services/batch_orchestrator_service/` directory. Example:

    ```env
    # BATCH_ORCHESTRATOR_SERVICE_PORT=5000 # If different from Docker Compose
    BATCH_ORCHESTRATOR_SERVICE_KAFKA_BOOTSTRAP_SERVERS=localhost:9093 # For local Kafka access outside Docker
    BATCH_ORCHESTRATOR_SERVICE_CONTENT_SERVICE_URL=http://localhost:8001/v1/content # For local Content Service
    BATCH_ORCHESTRATOR_SERVICE_LOG_LEVEL=DEBUG
    ```

    *Note: Adjust prefixes and port numbers based on your actual `config.py` and local setup.*

3. **Run the Service**:
    From the monorepo root:

    ```bash
    pdm run dev-batch
    ```

    This typically runs `pdm run -p services/batch_orchestrator_service dev` which in turn would execute a development server command defined in the service's `pyproject.toml`.

## Testing

Tests for this service should cover:

* API endpoint functionality.
* Correct event publishing (contract and content).
* Interaction with the Content Service (mocked).
* (Future) Command generation for ELS.

Run tests using Pytest, typically via a PDM script:

```bash
# Example: running tests for this service from monorepo root
pdm run pytest services/batch_orchestrator_service/tests/ -v
