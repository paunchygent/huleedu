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

### A.1. Enhance `topic_name()` Helper in Common Core

* **Objective**: Improve the developer experience and error diagnosability of the `topic_name()` helper.
* **Existing Code Context**: `common_core/src/common_core/enums.py` - `topic_name()` function.
    ```python
    # common_core/src/common_core/enums.py (current relevant part)
    # def topic_name(event: ProcessingEvent) -> str:
    #     topic_mapping = {
    #         ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
    #         ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED: "huleedu.essay.spellcheck.completed.v1",
    #     }
    #     if event not in topic_mapping:
    #         raise ValueError(
    #             f"Event '{event}' does not have an explicit topic mapping. "
    #             f"All events must have deliberate topic contracts defined in topic_mapping. "
    #             f"Available events: {list(topic_mapping.keys())}" # Current error message
    #         )
    #     return topic_mapping[event]
    ```
* **Suggested Refactoring**:
    1.  **Improve Error Message**: When an event is not found in `topic_mapping`, the `ValueError` message should list available `ProcessingEvent` enum members that *are* mapped, not just the keys of the `topic_mapping` if they are identical. More importantly, list the actual event-to-topic mappings.
    2.  **Enhance Docstring**: Update the `topic_name()` docstring to include the current `topic_mapping` table directly, making it visible on IDE hover.
* **Implementation Guide**:
    ```python
    # common_core/src/common_core/enums.py (suggested changes)
    # ... (ProcessingEvent enum and other parts of the file) ...

    _TOPIC_MAPPING = {
        ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED: "huleedu.essay.spellcheck.requested.v1",
        ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED: "huleedu.essay.spellcheck.completed.v1",
        # Add ALL other required mappings here
    }

    def topic_name(event: ProcessingEvent) -> str:
        """
        Convert a ProcessingEvent to its corresponding Kafka topic name.

        This centralizes topic naming. All events intended for Kafka MUST have an
        explicit mapping here to enforce architectural discipline.

        Args:
            event: The ProcessingEvent enum value.

        Returns:
            The Kafka topic name string.

        Raises:
            ValueError: If the event does not have an explicit topic mapping.

        Current Topic Mapping:
        ----------------------
        ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED ➜ "huleedu.essay.spellcheck.requested.v1"
        ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED ➜ "huleedu.essay.spellcheck.completed.v1"
        # (This table should be auto-generated or manually kept in sync in the docstring for documentation)
        # For dynamic generation in error message, see below.
        """
        if event not in _TOPIC_MAPPING:
            mapped_events_summary = "\n".join(
                [f"- {e.name} ({e.value}) ➜ '{t}'" for e, t in _TOPIC_MAPPING.items()]
            )
            raise ValueError(
                f"Event '{event.name} ({event.value})' does not have an explicit topic mapping. "
                f"All events intended for Kafka must have deliberate topic contracts defined. "
                f"Currently mapped events:\n{mapped_events_summary}"
            )
        return _TOPIC_MAPPING[event]
    ```
* **Key Files to Modify**: `common_core/src/common_core/enums.py`.
* **Acceptance Criteria**:
    * `ValueError` from `topic_name()` for an unmapped event includes a list of currently mapped events and their topics.
    * The docstring of `topic_name()` is updated to include (or clearly reference) the mapping table.

### A.2. Configure MyPy for External Libraries Without Type Stubs

* **Objective**: Eliminate MyPy warnings for `aiokafka` and `aiofiles` by configuring MyPy to handle missing type stubs appropriately, ensuring a cleaner CI type-checking process.
* **Implementation Guide**:
    1.  **Configure MyPy for Missing Stubs**: Add MyPy overrides to `pyproject.toml` to handle external libraries without official stubs:
        ```toml
        # pyproject.toml (root) - Add to [tool.mypy] section
        [[tool.mypy.overrides]]
        module = [
            "aiokafka.*",
            "aiofiles.*"
        ]
        ignore_missing_imports = true
        # Note: This is the recommended approach for external libraries without official stubs
        # We maintain strict typing for our own code while allowing flexibility for external deps
        ```
    2.  **Verify Configuration**: Run `pdm run typecheck-all` to confirm that warnings are resolved.
    3.  **Document Decision**: Add comment in `pyproject.toml` explaining why these specific modules are configured to ignore missing imports.
* **Key Files to Modify**: Root `pyproject.toml` (MyPy configuration only).
* **Acceptance Criteria**: 
    - `pdm run typecheck-all` no longer shows missing import warnings for `aiokafka` and `aiofiles`
    - MyPy configuration properly handles external libraries without compromising type safety for internal code
    - **CRITICAL**: No manual `pdm.lock` edits or local stub packages created

### A.3. Create Root `.dockerignore` File

* **Objective**: Speed up Docker image builds by preventing unnecessary files from being sent to the Docker daemon build context.
* **Implementation Guide**:
    1.  Create a `.dockerignore` file in the project root (`huledu-reboot/.dockerignore`).
    2.  Add common patterns for files and directories that should not be part of the build context for *any* service when the context is the repository root.
* **Content for `.dockerignore`**:
    ```
    # .dockerignore (at project root)
    __pycache__/
    *.pyc
    *.pyo
    *.pyd
    .Python
    env/
    venv/
    .venv/
    pip-cache/
    .pdm-build/
    .pdm-python # PDM's Python interpreter installations
    pdm.lock # Usually not needed in context if pyproject.toml is copied first
             # and pdm install is run in Docker. But can exclude if large.
    
    .git/
    .github/
    .vscode/
    .idea/
    *.swp
    *.swo
    
    # IDE and OS files
    .DS_Store
    Thumbs.db
    
    # Test files and reports (unless a specific Dockerfile needs test files for multi-stage builds)
    # This is a general ignore; if a Dockerfile *needs* tests (e.g. for a test stage),
    # it can still COPY them if this rule is not too broad or negated carefully.
    # For service builds, tests are typically not needed in the final image.
    tests/
    common_core/tests/
    services/**/tests/
    htmlcov/
    .pytest_cache/
    .coverage
    
    # Local development artifacts
    .local_content_store_mvp/ # Example from content_service dev
    *.log
    
    # Documentation / Tasks (usually not needed in service images)
    README.md
    TASKS/
    # .cursor/ # Rules are not needed in images
    ```
* **Key Files to Modify**: `.dockerignore` (New file at project root).
* **Acceptance Criteria**: Docker builds (e.g., `pdm run docker-build`) are noticeably faster due to a smaller build context being sent to the daemon. Verify by observing build output or context size.

---

## B. Core Phase 1.2 Implementation Tasks

### B.1. Implement Unit Tests for Spell Checker Worker (with DI & Context Manager)

* **Objective**: Ensure the `spell_checker_service` worker's core logic is robustly tested in isolation, using Dependency Injection (DI) for cleaner test setup and an async context manager for managing Kafka client states.
* **README.md Link/Rationale**: Implements **Service Autonomy** (README Sec 1), verifies adherence to **Explicit Contracts** (README Sec 1 & 3) and "Thin Events + Callback APIs" (README Sec 3). DI improves testability and maintainability. Context managers improve resource handling.

* **Refactoring `services/spell_checker_service/worker.py`**:
    1.  **Dependency Injection**: Modify `process_single_message` (or a similar core processing function) to accept `Workspace_content_func`, `store_content_func`, and `perform_spell_check_func` as injectable callables.
    2.  **Kafka Client State Management**: Refactor `spell_checker_worker_main` to use an `asynccontextmanager` for managing the `consumer_running` and `producer_running` states and the startup/shutdown of Kafka clients.

    ```python
    # services/spell_checker_service/worker.py (Suggested Refinements)
    import asyncio
    import json
    import logging
    import os
    from datetime import datetime, timezone
    from typing import Any, Callable, Awaitable, Optional, Tuple # Added Tuple
    from contextlib import asynccontextmanager # Added
    import aiohttp
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition, ConsumerRecord
    from aiokafka.errors import KafkaConnectionError
    from pydantic import ValidationError
    from dotenv import load_dotenv

    # ... (common_core imports as before) ...
    # SpellcheckRequestedDataV1, SpellcheckResultDataV1, EventEnvelope, EssayStatus, etc.

    load_dotenv()
    logger = logging.getLogger(__name__) # Use module-specific logger

    # Default implementations (can be overridden in tests or for different strategies)
    async def default_fetch_content(session: aiohttp.ClientSession, storage_id: str, essay_id: str) -> Optional[str]:
        return await fetch_content_from_service(session, storage_id, essay_id) # Your existing function

    async def default_store_content(session: aiohttp.ClientSession, text_content: str, essay_id: str) -> Optional[str]:
        return await store_content_to_service(session, text_content, essay_id) # Your existing function

    async def default_perform_spell_check(text: str, essay_id: str) -> Tuple[str, int]: # Ensure Tuple hint
        return await perform_spell_check(text, essay_id) # Your existing function


    async def process_single_message(
        msg: ConsumerRecord, # Type hint for Kafka message
        producer: AIOKafkaProducer,
        http_session: aiohttp.ClientSession,
        fetch_content_func: Callable[[aiohttp.ClientSession, str, str], Awaitable[Optional[str]]],
        store_content_func: Callable[[aiohttp.ClientSession, str, str], Awaitable[Optional[str]]],
        perform_spell_check_func: Callable[[str, str], Awaitable[Tuple[str, int]]] # Ensure Tuple hint
    ) -> bool: # True to commit, False to not (e.g. for retry, though current logic commits on error)
        logger.info(f"Processing msg from '{msg.topic}' p{msg.partition} o{msg.offset} key='{msg.key.decode() if msg.key else None}'")
        processing_started_at = datetime.now(timezone.utc)
        try:
            envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate(json.loads(msg.value.decode('utf-8'))) # Deserialize explicitly
            request_data = envelope.data
            essay_id = request_data.entity_ref.entity_id
            original_text_storage_id = request_data.text_storage_id

            original_text = await fetch_content_func(http_session, original_text_storage_id, essay_id)
            if original_text is None:
                logger.error(f"Essay {essay_id}: Could not fetch original text {original_text_storage_id}. Skipping.")
                return True # Commit

            corrected_text, corrections_count = await perform_spell_check_func(original_text, essay_id)

            corrected_text_storage_id = await store_content_func(http_session, corrected_text, essay_id)
            if corrected_text_storage_id is None:
                logger.error(f"Essay {essay_id}: Could not store corrected text. Skipping result event.")
                return True # Commit

            # ... (Construct SpellcheckResultDataV1 and EventEnvelope as before) ...
            # Example of constructing result_payload and result_envelope
            storage_meta = StorageReferenceMetadata()
            storage_meta.add_reference(ContentType.ORIGINAL_ESSAY, original_text_storage_id)
            storage_meta.add_reference(ContentType.CORRECTED_TEXT, corrected_text_storage_id)

            result_system_meta = SystemProcessingMetadata(
                entity=request_data.entity_ref,
                timestamp=datetime.now(timezone.utc),
                processing_stage=ProcessingStage.COMPLETED,
                event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                started_at=processing_started_at
            )
            result_payload = SpellcheckResultDataV1(
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                entity_ref=request_data.entity_ref,
                status=EssayStatus.SPELLCHECKED_SUCCESS,
                system_metadata=result_system_meta,
                original_text_storage_id=original_text_storage_id,
                storage_metadata=storage_meta,
                corrections_made=corrections_count
            )
            result_envelope = EventEnvelope[SpellcheckResultDataV1](
                event_type=OUTPUT_TOPIC, # Make sure OUTPUT_TOPIC is defined
                source_service=SOURCE_SERVICE_NAME, # Make sure SOURCE_SERVICE_NAME is defined
                correlation_id=envelope.correlation_id,
                data=result_payload
            )
            await producer.send_and_wait(
                OUTPUT_TOPIC,
                json.dumps(result_envelope.model_dump(mode="json")).encode('utf-8'), # Properly serialize to bytes
                key=essay_id.encode("utf-8")
            )
            logger.info(f"Essay {essay_id}: Published spellcheck result. Event ID: {result_envelope.event_id}")
            return True
        except ValidationError as ve: # Handle Pydantic validation error
            logger.error(f"Pydantic validation error processing msg at offset {msg.offset} from topic {msg.topic}: {ve.errors(include_url=False)}", exc_info=False)
            return True # Commit invalid message
        except Exception as e:
            logger.error(f"Generic error processing msg at offset {msg.offset} from topic {msg.topic}: {e}", exc_info=True)
            return True # Commit on other errors

    @asynccontextmanager
    async def kafka_clients(input_topic: str, consumer_group_id: str, client_id_prefix: str, bootstrap_servers: str):
        consumer = AIOKafkaConsumer(
            input_topic,
            bootstrap_servers=bootstrap_servers,
            group_id=consumer_group_id,
            client_id=f"{client_id_prefix}-consumer",
            value_deserializer=None, # Deserialize manually in process_single_message
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=f"{client_id_prefix}-producer",
            value_serializer=None, # Will serialize manually before sending
            acks="all",
            enable_idempotence=True, # Good practice
        )
        try:
            logger.info(f"Starting Kafka consumer for group {consumer_group_id} and producer...")
            await consumer.start()
            await producer.start()
            logger.info("Kafka clients started.")
            yield consumer, producer
        except KafkaConnectionError as kce:
            logger.critical(f"Failed to connect Kafka clients: {kce}", exc_info=True)
            raise # Reraise to prevent app from running in a broken state
        finally:
            logger.info("Stopping Kafka clients...")
            if producer._sender._running: # Check if producer actually started
                await producer.stop()
            if consumer._running: # Check if consumer actually started
                await consumer.stop()
            logger.info("Kafka clients stopped.")


    async def spell_checker_worker_main() -> None:
        # INPUT_TOPIC, CONSUMER_GROUP_ID, PRODUCER_CLIENT_ID (prefix), KAFKA_BOOTSTRAP_SERVERS from env/constants
        # Initialize constants like INPUT_TOPIC, OUTPUT_TOPIC, SOURCE_SERVICE_NAME, CONSUMER_GROUP_ID, CLIENT_ID_PREFIX, KAFKA_BOOTSTRAP_SERVERS
        # These should be defined at the module level, likely loaded from environment variables
        try:
            async with kafka_clients(INPUT_TOPIC, CONSUMER_GROUP_ID, PRODUCER_CLIENT_ID, KAFKA_BOOTSTRAP_SERVERS) as (consumer, producer):
                async with aiohttp.ClientSession() as http_session:
                    logger.info(f"Spell Checker Worker started. Consuming from '{INPUT_TOPIC}', group '{CONSUMER_GROUP_ID}'.")
                    async for msg in consumer: # type: ConsumerRecord
                        tp = TopicPartition(msg.topic, msg.partition)
                        offset_to_commit = msg.offset + 1
                        
                        # Pass default implementations of helper functions
                        processed_and_commit = await process_single_message(
                            msg, producer, http_session,
                            default_fetch_content, default_store_content, default_perform_spell_check
                        )
                        
                        if processed_and_commit:
                            await consumer.commit({tp: offset_to_commit})
                            logger.debug(f"Committed offset {offset_to_commit} for {tp}")
        except KafkaConnectionError:
            logger.critical("Exiting spell_checker_worker_main due to Kafka connection issues during startup.")
        except asyncio.CancelledError:
            logger.info("Spell Checker Worker main task was cancelled.")
        except Exception as e: # Catch any other unexpected errors in main setup/loop
            logger.critical(f"Spell Checker Worker critical error in main loop: {e}", exc_info=True)
        finally:
            logger.info("Spell Checker Worker main function finished.")

    # ... (fetch_content_from_service, store_content_to_service, perform_spell_check definitions remain as they were) ...
    # Make sure INPUT_TOPIC, OUTPUT_TOPIC, SOURCE_SERVICE_NAME etc. are defined (likely from os.getenv)
    # Example:
    # INPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
    # OUTPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)
    # SOURCE_SERVICE_NAME = "spell-checker-service"
    # CONSUMER_GROUP_ID = os.getenv("SPELLCHECKER_CONSUMER_GROUP", "spellchecker-service-group-v1.1")
    # PRODUCER_CLIENT_ID = "spellchecker-service" # Prefix for client_id
    # KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    ```
* **Implementation Guide (for tests in `services/spell_checker_service/tests/test_worker.py`)**:
    * Create fake/mock async versions of `Workspace_content_func`, `store_content_func`, `perform_spell_check_func`.
    * Call the refactored `process_single_message` with these fakes and mock Kafka/HTTP objects.
    * Assert behavior of fakes and the output/calls from `process_single_message`.
* **Acceptance Criteria**:
    * `worker.py` is refactored to use DI for core logic functions and an async context manager for Kafka clients.
    * Unit tests for `process_single_message` cover success and key failure paths using injected fake/mock functions.
    * Tests pass; code coverage for the core processing logic is high.

---

### B.2. Automate Kafka Topic Creation (with Docker Compose one-shot service)

* **🌐 NETWORK ACCESS REQUIRED**: Requires connection to Kafka cluster
* **Objective**: Implement a robust script for Kafka topic creation, runnable as a one-shot Docker Compose service for ensuring topics are present before other services start.
* **README.md Link/Rationale**: Supports **Event-Driven Communication Backbone** (README Sec 3).

* **Implementation Guide**:
    1.  Implement `scripts/kafka_topic_bootstrap.py` as per Task A.1 (and previous detailed response).
    2.  **Modify `docker-compose.yml`**: Add a one-shot service to run this script.
        ```yaml
        # docker-compose.yml (additions/modifications)
        services:
          # ... zookeeper, kafka definitions ...

          kafka_topic_setup:
            image: python:3.11-slim # Or your common base image if it has PDM/dependencies
            container_name: huleedu_kafka_topic_setup
            restart: "no" # Ensures it's a one-shot service
            depends_on:
              kafka:
                condition: service_healthy # Assumes Kafka has a healthcheck
            networks:
              - huleedu_internal_network
            volumes:
              - .:/app # Mount the whole project to access scripts and common_core
            working_dir: /app
            environment:
              - KAFKA_BOOTSTRAP_SERVERS=kafka:9092 # Internal Docker network address for Kafka
              - PYTHONPATH=/app/common_core/src:/app # To find common_core
            # Install minimal deps if base python image is used
            command: >
              sh -c "pip install aiokafka==0.10.0 && 
                     python scripts/kafka_topic_bootstrap.py"
            # If using an image with PDM and project already structured:
            # command: pdm run python scripts/kafka_topic_bootstrap.py
            # Or if PDM script is defined:
            # command: pdm run kafka-setup-topics

          # ... content_service, spell_checker_service, batch_service definitions ...
          # Make them depend on kafka_topic_setup for startup order
          content_service:
            depends_on:
              kafka_topic_setup: # Wait for topic setup to complete
                condition: service_completed_successfully
            # ... rest of content_service config
          spell_checker_service:
            depends_on:
              kafka_topic_setup:
                condition: service_completed_successfully
              content_service: # Existing dependency
                condition: service_healthy
            # ... rest of spell_checker_service config
          batch_service:
            depends_on:
              kafka_topic_setup:
                condition: service_completed_successfully
              content_service: # Existing dependency
                condition: service_healthy
            # ... rest of batch_service config
        ```
        *Note: Kafka itself (e.g., Bitnami image) might take time to be fully ready for admin client connections after its healthcheck passes. The bootstrap script should have retries or robust error handling for `KafkaConnectionError`.*
    3.  Ensure Kafka service in `docker-compose.yml` has an effective `healthcheck`. Bitnami Kafka images usually do.
* **Key Files to Modify**:
    * `scripts/kafka_topic_bootstrap.py` (as developed in A.1).
    * `docker-compose.yml` (Add `kafka_topic_setup` service, update `depends_on` for other services).
* **Acceptance Criteria**:
    * On `docker compose up`, the `kafka_topic_setup` service runs, creates topics, and exits successfully.
    * Other services start only after topic setup is complete.

---

### B.3. Implement Prometheus Scrape Endpoints (with Queue Latency Metric)

* **Objective**: Expose Prometheus metrics from HTTP services, including a "queue latency" metric for Kafka-consumed events where applicable.
* **README.md Link/Rationale**: Supports **Scalability & Maintainability** (README Sec 1) via observability for **Autonomous Services** (README Sec 1). Queue latency is a key operational metric.

* **Implementation Guide for HTTP Services (`content_service`, `batch_service`)**:
    1.  Follow guide from previous ticket response (Task 3) to add `prometheus-client`, `REQUESTS_TOTAL`, `REQUEST_LATENCY_SECONDS`, and the `/metrics` endpoint using `app.mount("/metrics", make_asgi_app(registry=REGISTRY))` for Quart apps.
* **Implementation Guide for "Queue Latency" (Example in `spell_checker_service`)**:
    * This metric makes most sense in services that *consume* from Kafka and then process.
    * **File**: `services/spell_checker_service/worker.py`
    * **Add Metric Definition**:
        ```python
        # services/spell_checker_service/worker.py (additions)
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
        #     # ...
        #     processing_started_at = datetime.now(timezone.utc) # Already there
        #     try:
        #         envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate(json.loads(msg.value.decode('utf-8')))
        #         
        #         # Calculate and record queue latency
        #         if hasattr(envelope, 'event_timestamp') and isinstance(envelope.event_timestamp, datetime):
        #             # Ensure event_timestamp is timezone-aware if processing_started_at is
        #             # Pydantic models from common_core should ensure UTC.
        #             queue_latency_seconds = (processing_started_at - envelope.event_timestamp).total_seconds()
        #             if queue_latency_seconds >= 0: # Avoid negative if clocks are skewed
        #                 KAFKA_QUEUE_LATENCY.labels(
        #                     topic=msg.topic, 
        #                     consumer_group=CONSUMER_GROUP_ID # Ensure CONSUMER_GROUP_ID is accessible
        #                 ).observe(queue_latency_seconds)
        #         # ... rest of the processing
        ```
    * **Exposing Metrics from Worker**: The `spell_checker_service` is a non-HTTP worker. To expose Prometheus metrics:
        1.  Option A: In `spell_checker_worker_main`, start a simple HTTP server in a separate async task using `prometheus_client.start_http_server(port, addr)`.
            ```python
            # In spell_checker_worker_main, before the main loop
            # from prometheus_client import start_http_server
            # import asyncio
            # METRICS_PORT = int(os.getenv("SPELLCHECKER_METRICS_PORT", "8001")) # Example port
            # # Start metrics server in background task to avoid blocking
            # asyncio.create_task(asyncio.to_thread(start_http_server, METRICS_PORT, "0.0.0.0"))
            # logger.info(f"Prometheus metrics server started on port {METRICS_PORT}")
            ```
        2.  Update its Dockerfile/`docker-compose.yml` to expose this metrics port.
        3.  **Note**: Ensure port uniqueness across service instances to avoid conflicts.
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

### B.4. Implement CI Smoke Test (with Docker Layer Caching)

* **🌐 NETWORK ACCESS REQUIRED**: Requires GitHub Actions setup, Docker Hub access, and CI/CD operations
* **Objective**: Create an automated CI smoke test for the core event flow, optimizing CI run time with Docker layer caching.
* **README.md Link/Rationale**: Validates **Event-Driven Architecture** (README Sec 1 & 3) and **Explicit Contracts** (README Sec 1 & 3). Caching improves CI efficiency.

* **Implementation Guide**:
    1.  Implement GitHub Actions workflow (`.github/workflows/smoke_test.yml`) and Python smoke test script (`tests/smoke/run_core_flow_smoke_test.py`) as per previous detailed response.
    2.  **Add Docker Layer Caching to GitHub Actions workflow**:
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
        #         # Ensure your `docker-build` script (pdm run docker compose build) uses BuildKit
        #         # And export cache to /tmp/.buildx-cache
        #         # Example: DOCKER_BUILDKIT=1 docker compose build --pull --cache-from type=local,src=/tmp/.buildx-cache --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max
        #         # After build, mv /tmp/.buildx-cache-new /tmp/.buildx-cache if changes occurred
        #         # This part needs careful setup of the build command to use actions/cache correctly.
        #         # A simpler but less effective Docker layer cache is often handled by BuildKit on self-hosted runners or Docker's own layer caching if using same runner.
        #         # For `actions/cache`, you need to explicitly manage the cache source/target for `docker buildx build`.

        #       # ... (rest of the steps: docker compose up, run smoke test, docker compose down) ...
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

### B.5. Implement 'EssayLifecycleService' (ELS) Skeleton (with Stub State Store)

* **Objective**: Create the ELS skeleton, now including a basic in-memory or SQLite stub state store to simulate essay state updates.
* **README.md Link/Rationale**: Initiates **ELS** implementation (README Sec 2), addresses **Batch/Essay Service Separation** (README Sec 2), and prepares for ELS's role in managing essay states (README Sec 4.B). A stub store allows for more meaningful initial logic.

* **Implementation Guide (`services/essay_lifecycle_service/worker.py`)**:
    1.  Follow the previous ELS skeleton setup guide (Task 5 from prior ticket).
    2.  **Add Stub State Store**:
        * For simplicity, start with an in-memory Python dictionary: `essay_states = {}` (global or class member in the worker).
        * Alternatively, for persistence across worker restarts (useful for local dev, but still a stub), use `sqlite3`.
    3.  **Enhance Message Handler**:
        * When an event like `SpellcheckResultDataV1` is consumed:
            * Extract `essay_id` and the new `status`.
            * Update the `essay_states` dictionary: `essay_states[essay_id] = {"status": status, "last_updated": datetime.now(timezone.utc), "spellcheck_details": event_data.model_dump()}`.
            * Log the update and the current (stubbed) state of the essay.
        ```python
        # services/essay_lifecycle_service/worker.py (conceptual additions for stub store)
        # ... (imports as before) ...
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
            # ... (rest of handler logic from previous skeleton)
        ```
* **Key Files to Modify**:
    * `services/essay_lifecycle_service/worker.py` (Add stub store logic).
    * Other ELS files (`pyproject.toml`, `Dockerfile`), `docker-compose.yml`, root `pyproject.toml` as per previous ELS skeleton setup.
* **Acceptance Criteria**:
    * ELS skeleton service consumes events (e.g., `SpellcheckResultDataV1`).
    * Updates its in-memory/SQLite stub state store with the essay's ID and new status/details.
    * Logs these updates.

---

## C. Key Architectural Nudges for Pre-Phase 2 Stability

These are general improvements to be applied across services or to `common_core` where appropriate.

### C.1. Structured Settings with Pydantic `BaseSettings`

* **Objective**: Standardize service configuration management using Pydantic's `BaseSettings` for type safety, defaults, and `.env` file loading.
* **Action**: For each service (`content_service`, `batch_service`, `spell_checker_service`, and new `essay_lifecycle_service`):
    * Create a `config.py` file (e.g., `services/content_service/config.py`).
    * Define a class inheriting from `pydantic_settings.BaseSettings`.
        ```python
        # Example: services/content_service/config.py
        from pydantic_settings import BaseSettings, SettingsConfigDict
        from pydantic import HttpUrl # If you have URL configs

        class ContentServiceSettings(BaseSettings):
            model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

            ENV_TYPE: str = "docker"
            CONTENT_STORE_ROOT_PATH: str = "/data/huleedu_content_store"
            PORT: int = 8000
            LOG_LEVEL: str = "INFO"
            # Add other config variables here with types and defaults
        
        settings = ContentServiceSettings() # Singleton instance
        ```
    * In service code (e.g., `app.py`, `worker.py`), import and use this `settings` object instead of direct `os.getenv()`.
    * Ensure `.env` files are supported for local development (Pydantic `BaseSettings` does this by default).
* **Rationale**: Typed configuration, validation, clear defaults, and .env support improve robustness and developer experience, aligning with maintainable service design.

### C.2. Enum JSON Serialization for API Models

* **Objective**: Ensure consistent enum serialization for any Pydantic models that might be directly returned via REST APIs (outside of an `EventEnvelope`).
* **Action**: If any service API endpoint directly returns a Pydantic model containing enums, ensure that model's `model_config` includes `json_encoders={Enum: lambda v: v.value}`.
    ```python
    # Example for a Pydantic model returned by an API
    # from pydantic import BaseModel
    # from enum import Enum
    #
    # class MyApiStatusEnum(str, Enum):
    #     ACTIVE = "active"
    #     INACTIVE = "inactive"
    #
            # class MyApiResponseModel(BaseModel):
        #     id: str
        #     api_status: MyApiStatusEnum
        #     model_config = ConfigDict(json_encoders={Enum: lambda v: v.value}) # Pydantic v2 syntax
    ```
* **Rationale**: Consistent enum representation across all external interfaces (events and APIs).

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
    1.  **Semantic Versioning**: Once ELS skeleton (Task B.5) is in and Phase 1.2 tasks are complete, plan to bump the versions of `huleedu-common-core` and all services from `0.1.0` to `0.2.0` (assuming these additions are non-breaking for existing consumers of 0.1.0 functionality). Document this decision and the trigger for future version bumps.
    2.  **`EventEnvelope` Schema Version**: Add a `schema_version` field to `common_core/src/common_core/events/envelope.py`.
        ```python
        # common_core/src/common_core/events/envelope.py (modification)
        # from pydantic import BaseModel, Field # , UUID, datetime, TypeVar, Generic, Optional
        # ...

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