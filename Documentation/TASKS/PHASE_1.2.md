# Task Ticket: Implement Core Phase 1.2 Enhancements & Architectural Refinements

**Ticket ID**: HULEDU-P1.2-CORE
**Date Created**: May 25, 2025
**Reporter**: Python Coding Companion (Incorporating User Feedback)
**Assignee**: Development Team

**Title**: Implement Core Phase 1.2 Enhancements: Detailed Refactoring, Observability, Testing, ELS Skeleton, and Architectural Polish

**Description**:
This ticket outlines the implementation of key Phase 1.2 tasks, building upon the successful completion of Phase 1.1. These tasks focus on enhancing testability, automating infrastructure, improving observability, introducing the Essay Lifecycle Service (ELS) skeleton, and incorporating several architectural micro-refinements. Completing these steps is critical for ensuring a robust, maintainable, and scalable foundation before proceeding to full Phase 2 (NLP & AI Feedback) development. All changes align with the HuleEdu `README.md` architectural blueprint.

**Overall Acceptance Criteria**:

* All sub-tasks (Foundational, Core, and Architectural Nudges where applicable as code changes) are completed and validated.
* All automated tests (new and existing) pass in CI.
* Code adheres to project standards (formatting, linting, typing per `.cursor/rules/050-python-coding-standards.mdc`).
* New configurations and scripts are functional and documented where necessary.

---

## A. Foundational Micro-Tweaks & Refinements

### A.1. Enhance `topic_name()` Helper in Common Core [COMPLETED]

* **Status**: COMPLETED

* **Summary**: The `topic_name()` helper in `common_core/src/common_core/enums.py` was enhanced. The `ValueError` message for unmapped events now lists all currently mapped events and their topics, improving diagnosability. The function's docstring was updated to include the current event-to-topic mapping table, making it easily accessible for developers.

### A.2. Configure MyPy for External Libraries Without Type Stubs [COMPLETED]

* **Status**: COMPLETED

* **Summary**: MyPy configuration in the root `pyproject.toml` was updated to ignore missing import errors for `aiokafka.*` and `aiofiles.*`. This resolves type-checking warnings for these external libraries that lack official type stubs, ensuring a cleaner CI process. A comment explaining this decision was added to the configuration.

### A.3. Create Root `.dockerignore` File [COMPLETED]

* **Status**: COMPLETED
* **Summary**: A root `.dockerignore` file was created in the project directory. This file includes common patterns for files and directories (e.g., `.git`, `__pycache__`, `venv/`, `.vscode/`, test artifacts, and documentation) to exclude them from Docker build contexts, thereby speeding up image builds.

---

## B. Core Phase 1.2 Implementation Tasks

### B.1. Implement Unit Tests for Spell Checker Worker (with DI & Context Manager) [COMPLETED]

* **Status**: COMPLETED

* **Objective**: Ensure the `spell_checker_service` worker's core logic is robustly tested in isolation, using Dependency Injection (DI) for cleaner test setup and an async context manager for managing Kafka client states.
* **README.md Link/Rationale**: Implements **Service Autonomy** (README Sec 1), verifies adherence to **Explicit Contracts** (README Sec 1 & 3) and "Thin Events + Callback APIs" (README Sec 3). DI improves testability and maintainability. Context managers improve resource handling.

* **Implementation Summary**:
    1. **Dependency Injection**: Successfully refactored `process_single_message` to accept injectable callables:
       * `fetch_content_func: FetchContentFunc`
       * `store_content_func: StoreContentFunc`
       * `perform_spell_check_func: PerformSpellCheckFunc`
    2. **Kafka Client State Management**: Implemented `kafka_clients` async context manager for proper Kafka client lifecycle management.
    3. **Comprehensive Test Suite**: Created 13 unit tests covering success/failure scenarios, event contract compliance, and correlation ID propagation.
    4. **Critical Issue Resolution**: Resolved Pydantic model rebuilding issues and established proper HTTP mocking patterns.

* **Key Implementation Details**:
    1. **Worker Refactoring**: Successfully implemented dependency injection pattern:

```python
async def process_single_message(
    msg: ConsumerRecord,
    producer: AIOKafkaProducer,
    http_session: aiohttp.ClientSession,
    fetch_content_func: FetchContentFunc,
    store_content_func: StoreContentFunc,
    perform_spell_check_func: PerformSpellCheckFunc,
) -> bool:
```

    2. **Async Context Manager**: Implemented `kafka_clients` for proper Kafka lifecycle management:

       ```python
       @asynccontextmanager
       async def kafka_clients(
           input_topic: str,
           consumer_group_id: str,
           client_id_prefix: str,
           bootstrap_servers: str,
       ) -> Any:
       ```

    3. **Test Suite Structure**:
       * `TestProcessSingleMessage`: 6 tests for core business logic with function-level mocking
       * `TestDefaultImplementations`: 5 tests for HTTP interaction functions with proper async context manager mocking
       * `TestEventContractCompliance`: 2 tests for Pydantic model validation and correlation ID propagation

    4. **Critical Issues Resolved**:
       * **Pydantic Model Rebuilding**: Fixed silent failures in forward reference resolution
       * **HTTP Mocking**: Established proper async context manager mocking patterns
       * **Import Order**: Resolved test environment import dependencies

* **Acceptance Criteria**: ✅ **COMPLETED**
  * `worker.py` refactored with DI for core logic functions and async context manager for Kafka clients
  * Comprehensive unit tests (13 tests) covering success/failure paths with proper mocking
  * All tests pass with high code coverage for core processing logic
  * Established reusable patterns for future service testing

---

### B.2. Automate Kafka Topic Creation (with Docker Compose one-shot service) [COMPLETED]

* **Status**: COMPLETED
* **🌐 NETWORK ACCESS REQUIRED**: Requires connection to Kafka cluster
* **Objective**: Implement a robust script for Kafka topic creation, runnable as a one-shot Docker Compose service for ensuring topics are present before other services start.
* **README.md Link/Rationale**: Supports **Event-Driven Communication Backbone** (README Sec 3).

* **Implementation Guide**:
    1. **Kafka Bootstrap Script**: Async topic creation with retry logic and dynamic topic discovery
    2. **Docker One-shot Service**: `kafka_topic_setup` service with proper dependencies
    3. **Service Dependencies**: All services depend on successful topic setup completion
* **Implementation Summary**:
    1. **Kafka Topic Bootstrap Script**: Successfully implemented `scripts/kafka_topic_bootstrap.py` with robust async topic creation, retry logic, and proper error handling
    2. **Docker Compose Integration**: Added `kafka_topic_setup` one-shot service with proper dependencies and health checks
    3. **Service Dependencies**: Updated all services to depend on successful topic setup completion
    4. **Critical Issue Resolution**: Resolved Docker container import issues by using absolute imports (`from config import settings`) instead of relative imports
    5. **MyPy Configuration**: Added module override for `config` module to handle monorepo vs container import differences

* **Key Implementation Details**:
    1. **Topic Bootstrap Service**: Creates all required Kafka topics dynamically from `common_core.enums.topic_name()`
    2. **Container Import Pattern**: Services use absolute imports for local modules because they run from service directories in containers
    3. **MyPy Compatibility**: Added `[[tool.mypy.overrides]]` for `config` module to ignore missing imports from monorepo root
    4. **Service Startup Order**: Kafka topic setup → Content Service → Batch Service & Spell Checker Service

* **Acceptance Criteria**: ✅ **COMPLETED**
  * On `docker compose up`, the `kafka_topic_setup` service runs, creates topics, and exits successfully
  * Other services start only after topic setup is complete
  * All services run properly with absolute imports for local configuration modules
  * MyPy type checking passes with proper module override configuration

### B.2.1. Rule Cleanup and Standardization [COMPLETED]

* **Status**: COMPLETED
* **Objective**: Clean up verbose rules to follow the clean, principle-focused pattern of good examples like `050-python-coding-standards.mdc` and `051-pydantic-v2-standards.mdc`.

* **Implementation Summary**:
    1. **Cleaned Verbose Rules**: Systematically reviewed and cleaned up verbose rules that didn't follow the clean, principle-focused pattern
    2. **Standardized Structure**: Applied consistent structure with clear sections, exact code snippets, and focused principles
    3. **Removed AI Slop**: Eliminated verbose prose and unnecessary explanations while maintaining essential information
    4. **Maintained Effectiveness**: Ensured rules remain effective and actionable while being more concise

* **Rules Cleaned**:
  * `110.4-debugging-mode.mdc`: Focused on "READ ERROR MESSAGES" principle with specific Docker import patterns
  * `040-service-implementation-guidelines.mdc`: Streamlined to core stack, async patterns, and essential guidelines
  * `070-testing-and-quality-assurance.mdc`: Condensed to core rules, testing patterns, and anti-patterns
  * `110.1-planning-mode.mdc`: Simplified to core process, requirements, and conflict resolution
  * `110.2-coding-mode.mdc`: Reduced to core standards, event-driven code, quality, and tool usage
  * `110.3-testing-mode.mdc`: Focused on core principles, priorities, debugging, and patterns
  * `110.5-refactoring-linting-mode.mdc`: Streamlined to standards, systematic approach, goals, and verification

* **Test Regression Resolution**:
    1. **Root Cause**: Monorepo import conflict where pytest imported wrong `config.py` files due to all service directories being in Python path
    2. **Proper Solution**: Used pytest's official `pythonpath` configuration to resolve import conflicts
    3. **Implementation**: Added `pythonpath = ["services/spell_checker_service", "services/content_service", "services/batch_service"]` to `pyproject.toml`
    4. **Result**: All 18 tests now pass without workarounds, mocks, or scripts

* **Acceptance Criteria**: ✅ **COMPLETED**
  * All verbose rules cleaned up to follow clean, principle-focused pattern
  * Rules maintain effectiveness while being more concise
  * Exact code snippets preserved where essential
  * Verbose prose and AI slop removed
  * Test regression fixed with proper architectural solution

---

### B.3.1 – Phase 1.2 Δ: Contracts & Containers (NEW)

This sub-phase introduces the protocol-based DI layer and prepares all services for observability and further pipelines.

PHASE 1 · 2 · 1 — "Contracts & Containers"
Sprint 1 extension · Version 1.0 · 2025-05-27
Status: Planned (all tasks NOT STARTED unless otherwise noted)

This micro-phase plugs in after Core B.5 of PHASE_1.2.md and
before "Key Architectural Nudges".
It lands the protocol-first DI layer, shrinks oversized modules,
and lays a metrics foundation required by B.3/B.5.

#### 0. Goals & Rationale 🎯

##### 1. Typed behavioural contracts (using typing.Protocol) in every running service

* **Why it matters**: Makes dependencies explicit, unlocks reliable mocks, raises MyPy's safety-net.

##### 2. Dishka DI container across Batch & Spell-Checker

* **Why it matters**: Replaces ad-hoc factories, leading to simpler wiring and consistent tests.

##### 3. File-size compliance (< 400 LoC, ≤ 100 chars/line)

* **Why it matters**: Keeps code legible and reviewable as features accrete.

##### 4. Unified metrics registry injected via DI

* **Why it matters**: Enables queue-latency Histogram now and future counters with zero refactor.

##### 5. EventEnvelope.schema_version + semantic package bump

* **Why it matters**: Formalizes future compatibility story.

#### 1. Task Matrix 📋

| Δ-ID | Title | Lead | Effort | Blockers | Status |
|------|-------|------|--------|----------|--------|
| Δ-5 | Add schema_version:int to EventEnvelope | Common-core | 0.5 d | — | ✅ |
| Δ-1 | Define service-local protocols.py bundles | Core team | 2-3 d | — | ✅ |
| Δ-3 | Refactor services/spell_checker_service/worker.py into ≤ 400 LoC siblings | Spell-Checker maint. | 1 d | Δ-1 | ✅ |
| Δ-2 | Wire Dishka providers in Batch & Spell-Checker | Core team | 1-2 d | Δ-1, Δ-3 | 🔴 |
| Δ-4 | Inject Prometheus registry + queue-latency metric | Infra guild | 1 d | Δ-2 | 🔴 |
| Δ-6 | Bump all internal packages to 0.2.0 (PDM) | Release eng. | 0.5 d | Δ-5 | 🔴 |

### B.4. Implement Prometheus Scrape Endpoints (with Queue Latency Metric) [NOT COMPLETED]

* **Status**: NOT COMPLETED
* **DEPENDS ON**: Δ-4 (Metrics Registry & Queue Latency)
* **Objective**: Expose Prometheus metrics from HTTP services, using the DI-managed metrics registry established in Δ-4.
* **README.md Link/Rationale**: Supports **Scalability & Maintainability** (README Sec 1) via observability for **Autonomous Services** (README Sec 1). Queue latency is a key operational metric.

* **Implementation Guide for HTTP Services (`content_service`, `batch_service`)**:
    1. Add `prometheus-client` to the respective `pyproject.toml` files. Implement the `/metrics` endpoint in each service's Quart `app.py`. This typically involves creating a `CollectorRegistry` (or using the default one), defining metrics like `REQUESTS_TOTAL` and `REQUEST_LATENCY_SECONDS`, and mounting the metrics application (e.g., `app.mount("/metrics", make_asgi_app(registry=REGISTRY))`). Refer to `prometheus-client` documentation for specific implementation details.
* **Implementation Guide for "Queue Latency" (Example in `spell_checker_service`)**:
  * This metric makes most sense in services that *consume* from Kafka and then process.
  * **File**: `services/spell_checker_service/worker.py`
  * **Add Metric Definition**:

    ```python
    from prometheus_client import Histogram # Assuming you'll expose metrics from worker
    # ...
    # This requires a way to expose metrics from the worker.
    # Could be start_http_server from prometheus_client in a separate thread/task,
    # or if the worker has any incidental HTTP component.
    # For now, let's define it. Exposition method is a sub-problem.
    KAFKA_QUEUE_LATENCY = Histogram(
        'kafka_message_queue_latency_seconds',
        'Latency between event timestamp and processing start',
        ['topic', 'consumer_group']
    )
    ```

  * **Record Metric in `process_single_message`**:

    ```python
    # services/spell_checker_service/worker.py (inside process_single_message)
    # async def process_single_message(...):
    #     processing_started_at = datetime.now(timezone.utc) # Already there
    #     try:
    #         envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate(json.loads(msg.value.decode('utf-8')))
    #         # ... (existing validation, extraction) ...
    #         if hasattr(envelope, 'event_timestamp') and isinstance(envelope.event_timestamp, datetime):
    #             # Record queue latency metric
    #             queue_latency_seconds = (processing_started_at - envelope.event_timestamp).total_seconds()
    #             if queue_latency_seconds >= 0: # Avoid negative if clocks are skewed
    #                 KAFKA_QUEUE_LATENCY.labels(
    #                     topic=msg.topic,
    #                     consumer_group=CONSUMER_GROUP_ID # Ensure CONSUMER_GROUP_ID is accessible
    ```

   **Exposing Metrics from Worker**: The `spell_checker_service` is a non-HTTP worker. To expose Prometheus metrics:
        1. Option A: In `spell_checker_worker_main`, start a simple HTTP server in a separate async task using `prometheus_client.start_http_server(port, addr)`.

```python
            # In spell_checker_worker_main, before the main loop
            # from prometheus_client import start_http_server
            # import asyncio
            # METRICS_PORT = int(os.getenv("SPELLCHECKER_METRICS_PORT", "8001")) # Example port
            # # Start metrics server in background task to avoid blocking
            # asyncio.create_task(asyncio.to_thread(start_http_server, METRICS_PORT, "0.0.0.0"))
            # logger.info(f"Prometheus metrics server started on port {METRICS_PORT}")
```

        2. Update its Dockerfile/`docker-compose.yml` to expose this metrics port.
        3. **Note**: Ensure port uniqueness across service instances to avoid conflicts.

* **Key Files to Modify**:
  * `services/content_service/app.py`, `services/content_service/pyproject.toml`
  * `services/batch_service/app.py`, `services/batch_service/pyproject.toml`
  * `services/spell_checker_service/worker.py` (add latency metric, start metrics server)
  * `services/spell_checker_service/pyproject.toml` (add `prometheus-client`)
  * `services/spell_checker_service/Dockerfile` (expose metrics port)
  * `docker-compose.yml` (expose metrics port for spell_checker_service).
* **Acceptance Criteria**:
  * `/metrics` endpoint available on HTTP services.
  * Spell checker service exposes metrics (including queue latency) on a configured port.
  * Metrics are in Prometheus format.

---

### B.5. Implement CI Smoke Test (with Docker Layer Caching) [NOT COMPLETED]

* **Status**: NOT COMPLETED
* **🌐 NETWORK ACCESS REQUIRED**: Requires GitHub Actions setup, Docker Hub access, and CI/CD operations
* **Objective**: Create an automated CI smoke test for the core event flow, optimizing CI run time with Docker layer caching.
* **README.md Link/Rationale**: Validates **Event-Driven Architecture** (README Sec 1 & 3) and **Explicit Contracts** (README Sec 1 & 3). Caching improves CI efficiency.

* **Implementation Guide**:
    1. Implement GitHub Actions workflow (`.github/workflows/smoke_test.yml`) and Python smoke test script (`tests/smoke/run_core_flow_smoke_test.py`) as per previous detailed response.
    2. **Add Docker Layer Caching to GitHub Actions workflow**:

    ```yaml
    # .github/workflows/smoke_test.yml (excerpt showing caching)
    # name: Smoke Test
    # on: [push] # Or pull_request
    # jobs:
    #   smoke-test:
    #     runs-on: ubuntu-latest
    #     steps:
    #       - name: Checkout code
    #         uses: actions/checkout@v3

    #       - name: Set up QEMU (for multi-platform builds, optional but good practice)
    #         uses: docker/setup-qemu-action@v2
    
    #       - name: Set up Docker Buildx
    #         uses: docker/setup-buildx-action@v2

    #       - name: Cache Docker layers
    #         uses: actions/cache@v3
    #         with:
    #           path: /tmp/.buildx-cache # Directory where buildx stores cache
    #           # Key includes hash of all Dockerfiles and relevant pyproject/lock files
    #           # This is a simplified example; a more robust key might involve hashing individual lock files too.
    #           key: ${{ runner.os }}-buildx-${{ github.sha }}-${{ hashFiles('**/Dockerfile', '**/pyproject.toml', '**/pdm.lock') }}
    #           restore-keys: |
    #             ${{ runner.os }}-buildx-${{ github.sha }}-
    #             ${{ runner.os }}-buildx-
    
    #       - name: Login to Docker Hub (if using private images, optional)
    #         # uses: docker/login-action@v2
    #         # with:
    #         #   username: ${{ secrets.DOCKERHUB_USERNAME }}
    #         #   password: ${{ secrets.DOCKERHUB_TOKEN }}

    #       - name: Set up Python and PDM
    #         # ... (your existing PDM setup steps) ...

    #       - name: Build Docker images with cache
    #         run: |
    #           pdm run docker-build --build-arg BUILDKIT_INLINE_CACHE=1 # For BuildKit to use the cache
    ```

    *Note: Effective Docker layer caching with `actions/cache` and `docker buildx` can be complex. Ensure your `docker-build` PDM script (which runs `docker compose build`) is compatible with Buildx cache export/import if you use this method. Simpler GitHub-managed Docker layer caching might apply if your runners provide it. The key is to investigate and implement the best caching strategy for your CI environment.*
* **Key Files to Modify**:
  * `.github/workflows/smoke_test.yml` (Add caching steps).
  * `tests/smoke/run_core_flow_smoke_test.py`
  * `docker-compose.yml` (Verify health checks).
* **Acceptance Criteria**:
  * CI smoke test runs and passes.
  * Subsequent CI runs are faster due to Docker layer caching (verify via CI logs/timings).

---

### B.6. Implement 'EssayLifecycleService' (ELS) Skeleton (with Stub State Store) [NOT COMPLETED]

* **Status**: NOT COMPLETED
* **DEPENDS ON**: Δ-1, Δ-2, Δ-3 (Protocols & DI Infrastructure)
* **Objective**: Create the ELS skeleton using the protocol-based DI architecture established in B.3, including a basic in-memory or SQLite stub state store to simulate essay state updates.
* **README.md Link/Rationale**: Initiates **ELS** implementation (README Sec 2), addresses **Batch/Essay Service Separation** (README Sec 2), and prepares for ELS's role in managing essay states (README Sec 4.B). A stub store allows for more meaningful initial logic.

* **Implementation Guide (`services/essay_lifecycle_service/worker.py`)**:
    1. Set up the basic ELS service structure: create `services/essay_lifecycle_service` directory with `worker.py`, `pyproject.toml` (including dependencies like `huleedu-common-core`, `aiokafka`, `pydantic-settings`), and a `Dockerfile`. Ensure it's added to the root `docker-compose.yml` and `pyproject.toml` for PDM visibility and an entrypoint script (e.g. `run-els-worker` in root pdm scripts that maps to `pdm run -p services/essay_lifecycle_service start_worker`) is created.
    2. **Add Stub State Store**:
        * For simplicity, start with an in-memory Python dictionary: `essay_states = {}` (global or class member in the worker).
        * Alternatively, for persistence across worker restarts (useful for local dev, but still a stub), use `sqlite3`.
    3. **Enhance Message Handler**:
        * When an event like `SpellcheckResultDataV1` is consumed:
            * Extract `essay_id` and the new `status`.
            * Update the `essay_states` dictionary: `essay_states[essay_id] = {"status": status, "last_updated": datetime.now(timezone.utc), "spellcheck_details": event_data.model_dump()}`.
            * Log the update and the current (stubbed) state of the essay.

        ```python
        # For an in-memory stub:
        essay_stub_store: Dict[str, Dict[str, Any]] = {} # essay_id -> {details}

        # async def handle_spellcheck_result(event_data: SpellcheckResultDataV1):
        #     essay_id = event_data.entity_ref.entity_id
        #     new_status = event_data.status
        #     logger.info(f"ELS: Received SpellcheckResult for Essay ID: {essay_id}, New Status: {new_status}")
            
        #     # Update stub store
        #     essay_stub_store[essay_id] = {
        #         "status": new_status,
        #         "spellcheck_result_payload": event_data.model_dump(mode="json"), # Store the whole payload for now
        #         "last_updated_els": datetime.now(timezone.utc).isoformat()
        #     }
        #     logger.info(f"ELS: Updated stub store for Essay ID: {essay_id}. Current stubbed state: {essay_stub_store.get(essay_id)}")
        ```

* **Key Files to Modify**:
  * `services/essay_lifecycle_service/worker.py` (Add stub store logic).
  * Other ELS files (`pyproject.toml`, `Dockerfile`), `docker-compose.yml`, root `pyproject.toml` as per previous ELS skeleton setup.
* **Acceptance Criteria**:
  * ELS skeleton service consumes events (e.g., `SpellcheckResultDataV1`).
  * Updates its in-memory/SQLite stub state store with the essay's ID and new status/details.
  * Logs these updates.

---

### B.3 – Phase 1.2 Δ: Contracts & Containers (FOUNDATIONAL REFACTORING)

This sub-phase introduces the protocol-based DI layer and prepares all services for observability and further pipelines. **CRITICAL**: Must be completed before B.4-B.6 as those tasks depend on this infrastructure.

**PHASE 1 · 2 · 1 — "Contracts & Containers"**  
Sprint 1 extension · Version 1.0 · 2025-05-27  
Status: Planned (all tasks NOT STARTED unless otherwise noted)

This micro-phase establishes the foundational architecture for DI, protocols, metrics, and file-size compliance that enables the subsequent implementation tasks.

#### 0. Goals & Rationale 🎯

##### 1. Typed behavioural contracts (using typing.Protocol) in every running service

* **Why it matters**: Makes dependencies explicit, unlocks reliable mocks, raises MyPy's safety-net.

##### 2. Dishka DI container across Batch & Spell-Checker

* **Why it matters**: Replaces ad-hoc factories, leading to simpler wiring and consistent tests.

##### 3. File-size compliance (< 400 LoC, ≤ 100 chars/line)

* **Why it matters**: Keeps code legible and reviewable as features accrete.

##### 4. Unified metrics registry injected via DI

* **Why it matters**: Enables queue-latency Histogram now and future counters with zero refactor.

##### 5. EventEnvelope.schema_version + semantic package bump

* **Why it matters**: Formalizes future compatibility story.

#### 1. Task Matrix 📋

| Δ-ID | Title | Lead | Effort | Blockers | Status |
|------|-------|------|--------|----------|--------|
| Δ-5 | Add schema_version:int to EventEnvelope | Common-core | 0.5 d | — | ✅ |
| Δ-1 | Define service-local protocols.py bundles | Core team | 2-3 d | — | ✅ |
| Δ-3 | Refactor services/spell_checker_service/worker.py into ≤ 400 LoC siblings | Spell-Checker maint. | 1 d | Δ-1 | ✅ |
| Δ-2 | Wire Dishka providers in Batch & Spell-Checker | Core team | 1-2 d | Δ-1, Δ-3 | 🔴 |
| Δ-4 | Inject Prometheus registry + queue-latency metric | Infra guild | 1 d | Δ-2 | 🔴 |
| Δ-6 | Bump all internal packages to 0.2.0 (PDM) | Release eng. | 0.5 d | Δ-5 | 🔴 |

**Legend**: 🔴 = Not started · 🟡 = In progress · ✅ = Done

#### 2. Detailed Task Break-down

**Δ-5 · EventEnvelope Version Field**

* In `common_core/src/common_core/events/envelope.py`:

    ```python
    from pydantic import BaseModel, Field
    from typing import TypeVar, Generic, Optional # ensure all needed imports
    from uuid import UUID, uuid4
    from datetime import datetime, timezone
    from enum import Enum # if used in model_config

    T_EventData = TypeVar("T_EventData", bound=BaseModel)

    class EventEnvelope(BaseModel, Generic[T_EventData]):
        event_id: UUID = Field(default_factory=uuid4)
        event_type: str
        event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
        source_service: str
        schema_version: int = 1 # Added field with default value
        correlation_id: Optional[UUID] = None
        data_schema_uri: Optional[str] = None # Existing field
        data: T_EventData
        model_config = { # Existing model_config
            "populate_by_name": True,
            "json_encoders": {Enum: lambda v: v.value},
        }
    ```

* Add `common_core/tests/test_event_envelope.py::test_schema_version_roundtrip` (or similar test file, perhaps in `common_core/tests/test_model_rebuilding.py`).

**Δ-1 · Protocols Everywhere**

* **Status**: ✅ Done
* **Objective**: Each running service owns a protocols.py exporting its key abstractions. Batch ➜ BatchRepositoryProtocol, BatchEventPublisherProtocol, Spell-Checker ➜ ContentClientProtocol, SpellLogicProtocol, etc.
* **Implementation Summary**:
  * Created `services/spell_checker_service/protocols.py` defining `ContentClientProtocol`, `SpellLogicProtocol`, `ResultStoreProtocol`, and `SpellcheckEventPublisherProtocol`.
  * Created `services/batch_service/protocols.py` defining `BatchRepositoryProtocol`, `BatchEventPublisherProtocol`, and `EssayLifecycleClientProtocol`.
  * Created `services/content_service/protocols.py` defining `ContentRepositoryProtocol` and `ContentEventPublisherProtocol`.
  * Protocols use concrete types (e.g., `AIOKafkaProducer`, `aiohttp.ClientSession`) where appropriate.
  * MyPy checks pass for these files and related services.
* **Implementation hints**:
  * Place in `services/<svc>/protocols.py`, no runtime code, just Protocol classes.
  * Run `pdm run mypy --strict --disallow-any-generics` monorepo-wide.
* **Acceptance**: CI passes; importing a service without its concrete deps under MyPy shows no errors.

**Δ-3 · Slim Worker**

* **Status**: ✅ Done
* Split current `services/spell_checker_service/worker.py` into:
  * `worker_main.py` (start, DI, metrics server) - 191 LoC
  * `event_router.py` (deserialise + dispatch, protocol implementations) - 338 LoC
  * `core_logic.py` (spell algorithm, HTTP helpers) - 105 LoC
* **Implementation Summary**:
  * Original `worker.py` (approx. 402 LoC) was successfully refactored and deleted.
  * `core_logic.py`: Contains fundamental, reusable functions for content fetching/storing and the spell check algorithm.
  * `event_router.py`: Handles main message processing (`process_single_message`), includes default protocol implementations, and routes Kafka records.
  * `worker_main.py`: Manages service startup, Kafka client lifecycle, signal handling, and the main consumption loop.
  * All new files are well under the 400 LoC limit.
  * No `from ... import *` used.
  * MyPy checks pass for `services/spell_checker_service/`.
  * All 13 unit tests in `services/spell_checker_service/tests/test_worker.py` were refactored for the new architecture and pass.
* Helper modules ≤ 150 LoC each.
* Remove any `from … import *`.

## Δ-2 · Dishka Wiring

* **Objective**: Replace manual factories.
* **Batch Service**
  * new `batch_service/di.py`
  * `BatchProvider(Provider)` binds KafkaBus, MetricsRegistry, BatchRepository…
  * `app.py` creates `container = make_container(BatchProvider())`.
* **Spell-Checker**
  * new `spell_checker_service/di.py` + change `worker_main.py` to `async with container.create_context()`.
* **Tests**: use `TestProvider` that binds mocks/stubs.
* **Commands**: `pdm run pytest -q` and `pdm run mypy --strict` must stay green.

## Δ-4 · Metrics Registry & Queue Latency

* **Registry binding**:

    ```python
    from dishka import Provider, provide
    from prometheus_client import CollectorRegistry

    class MetricsProvider(Provider):
        @provide(scope="singleton") # Or appropriate scope
        def registry(self) -> CollectorRegistry:
            return CollectorRegistry() # Or your custom registry
    ```

* **Worker metric** (example for `spell_checker_service/core_metrics.py`):

    ```python
    from prometheus_client import CollectorRegistry, Histogram

    def create_kafka_queue_latency_metric(registry: CollectorRegistry) -> Histogram:
        # This function would be defined in a metrics-specific module
        # and the resulting Histogram object would be provided by Dishka.
        return Histogram(
            'kafka_message_queue_latency_seconds',
            'Lag from event_timestamp to consume-start',
            ['topic', 'consumer_group'],
            registry=registry, # Injected registry
        )
    ```

* In `spell_checker_service/di.py`, inject `CollectorRegistry` into `create_kafka_queue_latency_metric` and provide the Histogram.
* Start HTTP exposition via `prometheus_client.start_http_server` in `spell_checker_service/worker_main.py` on `$SPELLCHECKER_METRICS_PORT` (default 8001).
* Verify with `curl localhost:8001/metrics | grep kafka_message_queue_latency_seconds`.

## Δ-6 · Package Version Bump

* Edit each relevant `pyproject.toml` (common_core, service_libs, all services):

    ```toml
    [project]
    version = "0.2.0"
    ```

* Run `pdm update --no-lock` to update metadata without changing locked dependencies if not necessary.
* Create a root `CHANGELOG.md` if one does not exist, or update the existing one with a summary of changes for v0.2.0, detailing the introduction of protocols, DI, metrics foundation, and EventEnvelope schema versioning.

#### 3. Sequencing 🗺️

```mermaid
graph TD
  S[Δ-5 Envelope Version] --> T[Δ-6 Package Bump];
  S --> A[Δ-1 Define Protocols];
  A --> C[Δ-3 Slim Worker];
  C --> B[Δ-2 Dishka Wiring];
  B --> D[Δ-4 Metrics Registry & Latency];

  subgraph "Enables Later Tasks"
    G[B.4 Prometheus Endpoints];
    H[B.5 ELS Skeleton];
  end
  
  D -.-> G; // Δ-4 enables B.4
  B -.-> H; // Δ-2 (and by extension Δ-1, Δ-3) enables B.5
```

* Δ-5 ("Envelope Version") is a prerequisite for Δ-6 ("Package Bump").
* Δ-1 ("Define Protocols") is the foundational step for Δ-3, Δ-2, and Δ-4.
* Δ-3 ("Slim Worker") should be done after protocols (Δ-1) are defined to guide the refactoring.
* Δ-2 ("Dishka Wiring") depends on protocols (Δ-1) and the refactored structure (Δ-3).
* Δ-4 ("Metrics Registry & Latency") depends on Dishka (Δ-2) for DI.
* The completion of this entire B.3 sub-phase, particularly Δ-4 and Δ-2/Δ-3, enables the subsequent B.4 and B.5 tasks respectively.

#### 4. Exit Criteria ✅

* `pdm run pytest`, `pdm run mypy --strict`, and `docker build` (or `pdm run docker-build`) in CI are green.
* Batch & Spell-Checker services start and log messages indicating Dishka container has bound providers (e.g., `dishka.container INFO Bound XX providers (schema_version=1)` or similar).
* `curl localhost:8001/metrics` (spell-checker metrics port) reports Prometheus text format, showing `kafka_message_queue_latency_seconds`.
* No Python file in the services exceeds 400 lines of code (LoC). A script like `scripts/loc_guard.sh` should be created and pass.
* Running `pdm show huleedu-common-core` (and for other updated packages) shows version 0.2.0.

#### 5. Rule-Book Amendments 📚

(These amendments will be applied to the respective rule files as detailed below, standardizing practices introduced or reinforced by the B.3 sub-phase)

Copy these bullets into `.cursor/rules/050-python-coding-standards.mdc` and `.cursor/rules/040-service-implementation-guidelines.mdc`.

**Dependency Injection** (relevant to `050-python-coding-standards.mdc` and `040-service-implementation-guidelines.mdc`)

* Use Dishka; every provider lives in `<service>/di.py` (ensures consistent DI setup introduced in Δ-2).
* Never import concrete classes inside business logic; depend on `typing.Protocol` (formalizes interface-based design from Δ-1).

**File Size & Line Length** (relevant to `050-python-coding-standards.mdc`)

* Hard ceiling: 400 LoC per `.py`, 100 chars per line (including docstrings) (enforces outcome of Δ-3).
* CI guard script: `scripts/loc_guard.sh` (automates compliance for file size).

**Metrics** (relevant to `040-service-implementation-guidelines.mdc`)

* Expose via `prometheus-client` only (standardizes metrics approach from Δ-4).
* Registry injected through DI, not instantiated ad-hoc (leverages DI setup from Δ-2 for metrics).

**PDM Commands** (relevant to `040-service-implementation-guidelines.mdc` or a new PDM-specific rule if preferred)

* Static checks: `pdm run mypy --strict`; tests: `pdm run pytest` (standardizes common development commands).
* Build images: `pdm run docker-build` (wrapper around `docker compose build`) (provides a consistent build interface).

**Versioning** (relevant to `081-pdm-dependency-management.mdc` or a general versioning rule)

* Increment `[project]` version on any additive change to Pydantic models or envelope (formalizes practice for Δ-5, Δ-6).

---

## C. Key Architectural Nudges for Pre-Phase 2 Stability

These are general improvements to be applied across services or to `common_core` where appropriate.

### C.1. Structured Settings with Pydantic `BaseSettings` [COMPLETED]

* **Status**: COMPLETED
* **Summary**: Standardized service configuration management using Pydantic's `BaseSettings` across all services. Added `pydantic-settings` dependency to `batch_service` and `spell_checker_service`. Created `config.py` files following the established pattern. Updated service code to use typed settings instead of direct `os.getenv()` calls. All services now have type-safe configuration with environment variable prefixing, `.env` file support, and proper defaults.
* **Implementation**:
  * ✅ Content Service: Already had proper implementation
  * ✅ Batch Service: Added config.py, updated app.py and hypercorn_config.py
  * ✅ Spell Checker Service: Added config.py, updated worker.py
  * 📋 Essay Service: Pattern established for future implementation
* **Pattern Reference**: See `.cursor/rules/040-service-implementation-guidelines.mdc` for standardized configuration pattern.

### C.2. Enum JSON Serialization for API Models [COMPLETED (Not Applicable)]

* **Status**: COMPLETED (Not Applicable - No current API endpoints return Pydantic models with enums)
* **Summary**: This task was to ensure Pydantic models returned by API endpoints correctly serialize enums as their values. A review of the `content_service` and `batch_service` API endpoints found no Pydantic models containing enums being directly returned. Therefore, no code changes were required.

### C.3. DLQ / Retry Strategy Consideration (Decision Point)

* **Objective**: Formulate an initial strategy for handling "poison pill" messages in Kafka consumers and transient errors.
* **Action**: This is a discussion and decision point for the team, not an immediate full implementation.
  * **Decision 1 (Poison Pills)**: For messages that repeatedly fail deserialization or cause unrecoverable business logic errors:
    * Option A (Simple): Log the error extensively, commit the offset, and move on. Risk of data loss if the message was important.
    * Option B (DLQ): After a few retries, publish the problematic message to a Dead-Letter Topic (e.g., `<original_topic>.DLT`). This requires a DLQ consumer or monitoring.
  * **Decision 2 (Transient Retries)**: For errors like temporary network issues when calling other services:
    * Implement a limited retry mechanism with exponential backoff within the consumer's message processing logic before giving up (and potentially sending to DLQ or just logging and committing). Libraries like `tenacity` can help.
  * **Initial Step for Phase 1.2**: For now, ensure all Kafka consumer message processing loops (e.g., in `spell_checker_service`, `els_skeleton`) have robust `try...except Exception` blocks that log detailed errors and *commit the offset* to prevent consumer blockage. Document this as the current "log and move on" strategy, with DLQ/retry as a planned enhancement.
* **Rationale**: Critical for service resilience. Prevents single bad messages from halting all processing.

### C.4. Version Bump Discipline & `EventEnvelope` Schema Version

* **Objective**: Establish practices for semantic versioning of packages and add schema versioning to the `EventEnvelope`.
* **Actions**:
    1. **Semantic Versioning**: Once ELS skeleton (Task B.6 - new numbering) is in and Phase 1.2 tasks are complete, plan to bump the versions of `huleedu-common-core` and all services from `0.1.0` to `0.2.0` (assuming these additions are non-breaking for existing consumers of 0.1.0 functionality). Document this decision and the trigger for future version bumps.
    2. **`EventEnvelope` Schema Version**: Add a `schema_version` field to `common_core/src/common_core/events/envelope.py`. (This is covered by Δ-5, so this part is duplicative but harmless here as a reminder of the principle).

        ```python
        class EventEnvelope(BaseModel, Generic[T_EventData]):
            event_id: UUID = Field(default_factory=uuid4)
            event_type: str
            event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
            source_service: str
            schema_version: int = 1 # Added field with default
            correlation_id: Optional[UUID] = None
            data_schema_uri: Optional[str] = None
            data: T_EventData
            model_config = {
                "populate_by_name": True,
                "json_encoders": {Enum: lambda v: v.value}, # Already there from Phase 1.1
            }
        ```

* **Rationale**: Semantic versioning clarifies compatibility and release management. `EventEnvelope.schema_version` aids in future-proofing event consumers, allowing them to handle different envelope structures if the envelope itself evolves (though `EventEnvelope.data` versioning is handled by `event_type` string).

---

This expanded ticket should provide the necessary detail and context for these next crucial steps.

### 🛠️ Potential Approaches/Implementation Details (Task B.3 Δ-8)
