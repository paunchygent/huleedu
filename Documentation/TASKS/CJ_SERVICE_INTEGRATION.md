# Task Ticket 1: Refactor and Adapt CJ Assessment Prototype into a Microservice

**Ticket ID:** `CJ_ASSESS_SVC_REFACTOR_001`
**Title:** Refactor Comparative Judgment Prototype into `cj_assessment_service` Microservice
**Sprint Goal:** Develop a focused, event-driven `cj_assessment_service` that integrates into the HuleEdu ecosystem, adhering to established architectural principles, DI patterns, and data handling strategies.

## 🎯 **OVERALL PROGRESS STATUS** 

### **COMPLETED PHASES:**

✅ **Common Core Event Contracts (Ticket 2, Phase 1)** - All event models, enums, and topic mappings implemented  
✅ **Service Scaffolding (Ticket 1, Phase 1)** - Complete directory structure, configs, protocols, and Docker integration  

### **READY FOR IMPLEMENTATION:**

🟡 **Next Phase:** Ticket 1, Phase 2 - Data Models and Protocol Implementation  
🟡 **Next Phase:** Ticket 2, Phase 2 - BOS Updates for CJ Pipeline  

### **ARCHITECTURAL FOUNDATION:**

- CJ Assessment Service skeleton with all dependencies and configuration ✅
- Protocol-based clean architecture interfaces defined ✅  
- Event contracts for CJ assessment workflow established ✅
- Docker containerization and service integration complete ✅
- All components pass linting, type checking, and build successfully ✅

**Description:**
The existing `cj_essay_assessment` CLI prototype needs to be refactored into a dedicated microservice named `cj_assessment_service`. This service will be responsible for performing comparative judgment on batches of spellchecked essays. It will consume requests via Kafka, process essays using LLM-based comparisons, store results in its own database, and publish outcomes. The LLM calling logic will be abstracted via a protocol. The service must follow the architectural patterns (Dishka for DI, protocol-first, Kafka worker) established in other HuleEdu services like the `spell_checker_service`.

**Key Design Decisions Incorporated:**

* No internal spell-checking or NLP; assumes input essay texts are already spell-checked.
* LLM interaction logic abstracted via `LLMInteractionProtocol`.
* Database models (`models_db.py`) adapted:
  * `ProcessedEssay.els_essay_id` (string UUID from ELS) will be the primary functional key.
  * `ProcessedEssay.assessment_input_text` will store the fetched spellchecked text.
  * `CJBatchUpload` tracks CJ jobs, stores `bos_batch_id` and event `correlation_id` for traceability. Each assessment request creates a new `CJBatchUpload` record.
  * `user_id` and `original_filename` are removed from CJ service's core essay/batch data. `class_designation` is deferred (YAGNI).
* Input Event: `ELS_CJAssessmentRequestV1` (defined in `common_core`).
* Output Event: `CJAssessmentCompletedV1` (to be defined in `common_core`).

---

### Phase 1: Service Scaffolding and Basic Setup

**Goal:** Establish the foundational directory structure, project configuration, Docker setup, and initial DI for the `cj_assessment_service`.

**Affected Files/Structure:**

* `services/cj_assessment_service/` (new directory)
* `services/cj_assessment_service/pyproject.toml` (new)
* `services/cj_assessment_service/Dockerfile` (new)
* `services/cj_assessment_service/README.md` (new, basic)
* `services/cj_assessment_service/config.py` (new)
* `services/cj_assessment_service/protocols.py` (new, empty or with initial protocol shells)
* `services/cj_assessment_service/di.py` (new, basic `ServiceProvider` for Dishka)
* `services/cj_assessment_service/worker_main.py` (new, basic shell)
* `services/cj_assessment_service/event_processor.py` (new, basic shell)
* `root pyproject.toml`: Add `cj_assessment_service` to `[dependency-groups.dev]` and PDM scripts.
* `docker-compose.yml`: Add entry for `cj_assessment_service`.

**Implementation Instructions:**

1. **Create Directory:** `mkdir services/cj_assessment_service`
2. **`pyproject.toml`:**
    * Adapt from an existing service (e.g., `spell_checker_service/pyproject.toml`).
    * Dependencies: `aiokafka`, `aiohttp`, `python-dotenv`, `huleedu-common-core`, `huleedu-service-libs`, `pydantic`, `pydantic-settings`, `prometheus-client`, `dishka`, `SQLAlchemy[asyncio]`, `aiosqlite` (or your chosen async DB driver), `cachetools`, `diskcache`, `choix`, `numpy`, `tenacity`.
    * PDM scripts: `start_worker`.
3. **`Dockerfile`:**
    * Adapt from `spell_checker_service/Dockerfile`. Ensure it copies necessary files and installs dependencies using PDM.
    * CMD should be `["pdm", "run", "start_worker"]`.
4. **`config.py`:**
    * Define `Settings(BaseSettings)` for `cj_assessment_service`.
    * Include: `LOG_LEVEL`, `SERVICE_NAME`, `KAFKA_BOOTSTRAP_SERVERS`, `CONSUMER_GROUP_ID_CJ`, `PRODUCER_CLIENT_ID_CJ`, input/output topic names (e.g., `CJ_ASSESSMENT_REQUEST_TOPIC`, `CJ_ASSESSMENT_COMPLETED_TOPIC`), `CONTENT_SERVICE_URL`, `DATABASE_URL_CJ`, LLM provider settings, comparison loop settings (`max_pairwise_comparisons`, etc.), `METRICS_PORT`.
    * Use `env_prefix="CJ_ASSESSMENT_SERVICE_"`.
5. **`di.py`:**
    * Create `CJAssessmentServiceProvider(Provider)`.
    * Include basic providers for `Settings` and `CollectorRegistry`.

    ```python
    # services/cj_assessment_service/di.py
    from dishka import Provider, Scope, provide
    from .config import Settings, settings as service_settings
    from prometheus_client import CollectorRegistry

    class CJAssessmentServiceProvider(Provider):
        @provide(scope=Scope.APP)
        def provide_settings(self) -> Settings:
            return service_settings

        @provide(scope=Scope.APP)
        def provide_metrics_registry(self) -> CollectorRegistry:
            return CollectorRegistry()
        # More providers will be added in later phases
    ```

6. **`worker_main.py` & `event_processor.py` Shells:** Create empty files or basic structures.
7. **Update Monorepo Config:**
    * Add `"-e file:///${PROJECT_ROOT}/services/cj_assessment_service"` to `[dependency-groups.dev]` in root `pyproject.toml`.
    * Add PDM script e.g., `run-cj-assessment = "pdm run -p services/cj_assessment_service start_worker"`.
    * Add `cj_assessment_service` to `docker-compose.yml` (depending on Kafka, Content Service).

**Phase 1 Checklist: ✅ COMPLETED**

* [x] `cj_assessment_service` directory and basic file structure created.
* [x] `pyproject.toml` configured with dependencies and PDM scripts.
* [x] `Dockerfile` created and service builds successfully.
* [x] `config.py` with `Settings` class defined.
* [x] Basic `di.py` with `CJAssessmentServiceProvider` exists.
* [x] Service added to `docker-compose.yml` with proper configuration.

**Implementation Status:** Phase 1 is COMPLETE. The CJ Assessment Service has been scaffolded with:
- Complete directory structure following HuleEdu patterns
- Working pyproject.toml with all required dependencies (aiokafka, aiohttp, dishka, SQLAlchemy, choix, etc.)
- Pydantic-based configuration system with environment variable support
- Protocol interfaces for clean architecture (ContentClientProtocol, LLMInteractionProtocol, CJDatabaseProtocol, CJEventPublisherProtocol)
- Basic Dishka DI provider setup
- Worker main entry point and event processor shells
- Docker image that builds successfully
- Integration with docker-compose.yml

---

### Phase 2: Define Protocols and Adapt Data Models

**Goal:** Establish all necessary `typing.Protocol` interfaces and adapt the prototype's database models (`models_db.py`) according to the refined strategy.

**Affected Files:**

* `services/cj_assessment_service/protocols.py` (new content)
* `services/cj_assessment_service/models_db.py` (adapted from prototype)
* `services/cj_assessment_service/enums_db.py` (new, for `CJBatchStatusEnum` etc.)
* `services/cj_assessment_service/models_api.py` (adapted from prototype, if `EssayForComparison.id` changes to `str`)

**Implementation Instructions:**

1. **`protocols.py`:** Define the following protocols:
    * `ContentClientProtocol`: For fetching spellchecked essay text.

        ```python
        class ContentClientProtocol(Protocol):
            async def fetch_content(self, storage_id: str) -> str: ... # Returns text directly
        ```

    * `LLMInteractionProtocol`: For performing comparisons.

        ```python
        from ..models_api import ComparisonTask, ComparisonResult # Assuming models_api.py is in the same service dir
        class LLMInteractionProtocol(Protocol):
            async def perform_comparisons(self, tasks: List[ComparisonTask]) -> List[ComparisonResult]: ...
        ```

    * `CJDatabaseProtocol`: For all database interactions specific to CJ.

        ```python
        from sqlalchemy.ext.asyncio import AsyncSession
        from contextlib import asynccontextmanager
        from typing import AsyncGenerator, List, Dict, Any, Optional
        from uuid import UUID
        from .models_db import CJBatchUpload, ProcessedEssay as CJ_ProcessedEssay, ComparisonPair as CJ_ComparisonPair
        from .enums_db import CJBatchStatusEnum

        class CJDatabaseProtocol(Protocol):
            @asynccontextmanager
            async def session(self) -> AsyncGenerator[AsyncSession, None]: ...

            async def create_new_cj_batch(
                self, session: AsyncSession, bos_batch_id: str, event_correlation_id: Optional[str],
                language: str, course_code: str, essay_instructions: str,
                initial_status: CJBatchStatusEnum, expected_essay_count: int
            ) -> CJBatchUpload: ...
            
            async def create_or_update_cj_processed_essay(
                self, session: AsyncSession, cj_batch_id: int, els_essay_id: str,
                text_storage_id: str, assessment_input_text: str
            ) -> CJ_ProcessedEssay: ...

            async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> List[CJ_ProcessedEssay]: ...
            
            async def get_comparison_pair_by_essays(self, session: AsyncSession, cj_batch_id: int, essay_a_els_id: str, essay_b_els_id: str) -> Optional[CJ_ComparisonPair]: ...
            
            async def store_comparison_results(self, session: AsyncSession, results: List[ComparisonResult], cj_batch_id: int) -> None: ... # Simplified, might need more detail
            
            async def update_essay_scores_in_batch(self, session: AsyncSession, cj_batch_id: int, scores: Dict[str, float]) -> None: ... # scores keyed by els_essay_id
            
            async def update_cj_batch_status(self, session: AsyncSession, cj_batch_id: int, status: CJBatchStatusEnum) -> None: ...
            
            async def get_final_cj_rankings(self, session: AsyncSession, cj_batch_id: int) -> List[Dict[str, Any]]: ...
            
            async def initialize_db_schema(self) -> None: ...
        ```

    * `CJEventPublisherProtocol`: For publishing results.

        ```python
        from common_core.events.cj_assessment_events import CJAssessmentCompletedV1 # To be defined in common_core
        from uuid import UUID
        class CJEventPublisherProtocol(Protocol):
            async def publish_assessment_completed(self, completion_data: CJAssessmentCompletedV1, correlation_id: Optional[UUID]) -> None: ...
            async def publish_assessment_failed(self, failure_data: Any, correlation_id: Optional[UUID]) -> None: ... # Define CJAssessmentFailedV1
        ```

2. **`enums_db.py`:** Define `CJBatchStatusEnum` (e.g., `PENDING`, `FETCHING_CONTENT`, `PERFORMING_COMPARISONS`, `COMPLETE_STABLE`, `COMPLETE_MAX_COMPARISONS`, `ERROR_PROCESSING`, `ERROR_ESSAY_PROCESSING`).
3. **`models_db.py`:**
    * Adapt `BatchUpload` to `CJBatchUpload`:
        * Primary Key: `id: Mapped[int]`.
        * Add fields: `bos_batch_id: Mapped[str]`, `event_correlation_id: Mapped[str | None]`, `language: Mapped[str]`, `course_code: Mapped[str]`, `essay_instructions: Mapped[str]`.
        * Remove `user_id`. `class_designation` deferred.
        * `status` uses new `CJBatchStatusEnum`.
    * Adapt `ProcessedEssay`:
        * Primary Key: `els_essay_id: Mapped[str] = mapped_column(String(36), primary_key=True)`.
        * Foreign Key: `cj_batch_id: Mapped[int] = mapped_column(ForeignKey("cj_batch_uploads.id"))`.
        * Rename `original_content` to `assessment_input_text: Mapped[str]`.
        * Add `text_storage_id: Mapped[str]`.
        * Remove `original_filename`. Omit NLP fields or mark as not populated by this service.
    * Adapt `ComparisonPair`:
        * Foreign Keys `essay_a_els_id` and `essay_b_els_id` to reference `ProcessedEssay.els_essay_id` (string type).
        * Foreign Key `cj_batch_id` to reference `CJBatchUpload.id`.
    * Define a common `Base` for these models.
4. **`models_api.py`:**
    * Update `EssayForComparison.id` to be `str` to hold `els_essay_id`.
    * Ensure `ComparisonTask` and `ComparisonResult` are compatible with this change.

**Phase 2 Checklist:**

* [ ] All required protocols defined in `protocols.py`.
* [ ] `models_db.py` updated with `CJBatchUpload`, `ProcessedEssay`, `ComparisonPair` reflecting new PK strategy, field names, and relationships.
* [ ] `enums_db.py` created with `CJBatchStatusEnum`.
* [ ] `models_api.py` (if used for internal structuring) adapted for string `els_essay_id`.

---

### Phase 3: Adapt Core Logic Modules

**Goal:** Migrate and adapt the business logic from the prototype's `pair_generator.py`, `ranking_handler.py` to new service modules, and prepare the LLM interaction logic. These modules should operate based on the defined protocols and new data models (especially string UUIDs for essay IDs).

**Affected Files:**

* `services/cj_assessment_service/pair_generation.py` (new, from prototype's `pair_generator.py`)
* `services/cj_assessment_service/scoring_ranking.py` (new, from prototype's `ranking_handler.py`)

**Implementation Instructions:**

1. **`pair_generation.py`:**
    * Copy logic from `cj_essay_assessment/pair_generator.py`.
    * Adapt `generate_comparison_tasks` function:
        * Input `essays_for_comparison: List[EssayForComparison]` will now have `essay.id` as a string (ELS essay ID).
        * `db_session: AsyncSession` will be passed in.
        * `batch_id` parameter will be the internal integer `cj_batch_id`.
        * Calls to `_fetch_existing_comparison_ids` (or similar logic now part of `CJDatabaseProtocol`) will use the `db_session` and `cj_batch_id`, and work with `essay_a_els_id`, `essay_b_els_id`.
2. **`scoring_ranking.py`:**
    * Copy logic from `cj_essay_assessment/ranking_handler.py`.
    * Adapt `record_comparisons_and_update_scores`:
        * `all_essays: List[EssayForComparison]` (IDs are string ELS IDs).
        * `db_handler` parameter replaced with `db_session: AsyncSession`.
        * `batch_id` parameter is the internal integer `cj_batch_id`.
        * Database interactions (storing `ComparisonPair`, updating `ProcessedEssay.current_bt_score`) must go through `db_session` using the adapted SQLAlchemy models. E.g., when fetching/updating `ProcessedEssay`, use `els_essay_id`.
        * The score dictionary `current_bt_scores` will be keyed by `els_essay_id` (string).
    * Adapt `check_score_stability`: Operates on score dictionaries keyed by `els_essay_id` (string).
    * Adapt `get_essay_rankings`: Uses `db_session` and internal `cj_batch_id`. Returns rankings possibly with `els_essay_id`.
3. **Review ID Handling:** Carefully review all parts of these modules that deal with essay IDs to ensure they correctly handle the `els_essay_id` (string) for logic and use the internal integer `ProcessedEssay.id` only if strictly necessary for ORM relationships within the CJ DB context (though direct use of `els_essay_id` as PK is preferred). If `els_essay_id` is PK, then `EssayForComparison.id` is string, and all dicts of scores are keyed by string.

**Phase 3 Checklist:**

* [ ] `pair_generation.py` logic adapted to use `AsyncSession` and string `els_essay_id`.
* [ ] `scoring_ranking.py` logic adapted to use `AsyncSession` and string `els_essay_id`.
* [ ] Logic correctly handles `EssayForComparison.id` as string.
* [ ] Score dictionaries use string `els_essay_id` as keys.

---

### Phase 4: Implement Protocol Adapters and DI Providers

**Goal:** Create concrete implementations for all defined protocols and set up Dishka providers in `di.py`.

**Affected Files:**

* `services/cj_assessment_service/implementations/__init__.py`
* `services/cj_assessment_service/implementations/content_client_impl.py` (new)
* `services/cj_assessment_service/implementations/llm_interaction_impl.py` (new, from prototype's `llm_caller.py` and `utils/llm_utils.py`)
* `services/cj_assessment_service/implementations/db_access_impl.py` (new, from prototype's `db_handler.py`)
* `services/cj_assessment_service/implementations/event_publisher_impl.py` (new)
* `services/cj_assessment_service/di.py` (updated)

**Implementation Instructions:**

1. **`implementations/content_client_impl.py`:**
    * Implement `ContentClientProtocol`.
    * Constructor takes `aiohttp.ClientSession` and `Settings`.
    * `fetch_content` makes GET request to `settings.CONTENT_SERVICE_URL`.
2. **`implementations/llm_interaction_impl.py`:**
    * Implement `LLMInteractionProtocol`.
    * Constructor takes `aiohttp.ClientSession` and `Settings`.
    * Move and adapt classes `CacheManager`, `BaseLLMProvider` (and its children) from the prototype's `llm_caller.py`.
    * Move and adapt `call_llm_api_with_retry` from `utils/llm_utils.py`.
    * The `perform_comparisons` method will orchestrate `process_comparison_tasks_async` logic.
3. **`implementations/db_access_impl.py`:**
    * Implement `CJDatabaseProtocol`.
    * Constructor takes `Settings` (for `DATABASE_URL_CJ`).
    * Adapt methods from prototype's `DatabaseHandler` class to match protocol, using adapted `models_db.py`.
    * Include `initialize_db_schema` method to create tables.
    * Ensure `session` context manager is implemented.
4. **`implementations/event_publisher_impl.py`:**
    * Implement `CJEventPublisherProtocol`.
    * Constructor takes `AIOKafkaProducer` and `Settings`.
    * `publish_assessment_completed` sends `CJAssessmentCompletedV1` to `settings.CJ_ASSESSMENT_COMPLETED_TOPIC`.
    * `publish_assessment_failed` sends a failure event.
5. **`di.py`:** Update `CJAssessmentServiceProvider`:
    * Add providers for `AIOKafkaProducer` and `aiohttp.ClientSession` (APP scope).
    * Add providers for each protocol, returning instances of the new `_impl.py` classes, injecting their dependencies (e.g., session, producer, settings).

    ```python
    # services/cj_assessment_service/di.py
    # ... (imports for Provider, Scope, provide, Settings, protocols, implementations) ...
    # ... (imports for AIOKafkaProducer, ClientSession) ...

    class CJAssessmentServiceProvider(Provider):
        # ... existing providers for settings, registry ...

        @provide(scope=Scope.APP)
        async def provide_kafka_producer(self, settings: Settings) -> AIOKafkaProducer:
            producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS, client_id=f"{settings.SERVICE_NAME}-producer")
            await producer.start()
            return producer

        @provide(scope=Scope.APP)
        async def provide_http_session(self) -> ClientSession:
            # Consider configuring timeouts, connection limits here
            return ClientSession()

        @provide(scope=Scope.APP)
        def provide_content_client(self, session: ClientSession, settings: Settings) -> ContentClientProtocol:
            return DefaultContentClientImpl(session, settings) # Assuming Default...Impl is the class name

        @provide(scope=Scope.APP)
        def provide_llm_interaction(self, session: ClientSession, settings: Settings) -> LLMInteractionProtocol:
            return DefaultLLMInteractionImpl(session, settings)

        @provide(scope=Scope.APP)
        async def provide_db_protocol(self, settings: Settings) -> CJDatabaseProtocol:
            db_impl = DefaultCJDatabaseImpl(settings) # DefaultCJDatabaseImpl is your class name
            await db_impl.initialize_db_schema() # Initialize schema at startup
            return db_impl
            
        @provide(scope=Scope.APP)
        def provide_event_publisher(self, producer: AIOKafkaProducer, settings: Settings) -> CJEventPublisherProtocol:
            return DefaultCJEventPublisherImpl(producer, settings)
    ```

**Phase 4 Checklist:**

* [ ] All protocol implementations created in `implementations/` directory.
* [ ] `LLMInteractionProtocol` implementation encapsulates `llm_caller.py` and `utils/llm_utils.py` logic.
* [ ] `CJDatabaseProtocol` implementation adapts `db_handler.py` logic and uses updated models.
* [ ] `di.py` correctly provides all dependencies using Dishka.
* [ ] Database schema initialization is handled.

---

### Phase 5: Implement `core_assessment_logic.py`

**Goal:** Implement the `run_cj_assessment_workflow` function as outlined previously, orchestrating the CJ process using the injected protocols and adapted logic modules.

**Affected Files:**

* `services/cj_assessment_service/core_assessment_logic.py` (new content)

**Implementation Instructions:**

1. **Implement `run_cj_assessment_workflow`:**
    * Signature: `async def run_cj_assessment_workflow(request_event_data: ELS_CJAssessmentRequestV1, db_protocol: CJDatabaseProtocol, content_protocol: ContentClientProtocol, llm_protocol: LLMInteractionProtocol, settings: Settings) -> Tuple[RankingResultType, DetailedResultsRefType]:`
    * **Step 1: Initialize Internal CJ Batch:**
        * Call `db_protocol.create_new_cj_batch(...)` using data from `request_event_data`.
    * **Step 2: Fetch and Store Essay Texts:**
        * Loop through `request_event_data.essays_for_cj`.
        * For each, call `content_protocol.fetch_content(text_storage_id)`.
        * Call `db_protocol.create_or_update_cj_processed_essay(...)` to save the fetched text and link to the internal CJ batch, using `els_essay_id` as the key.
        * Build the `List[EssayForComparison]` (with string IDs) for the comparison loop. Handle fetching errors.
    * **Step 3: Iterative Comparison Loop:**
        * Adapt loop from prototype's `main.py`.
        * Call `pair_generation.generate_comparison_tasks(...)`, passing the `db_protocol.session()` context and `List[EssayForComparison]`.
        * Call `llm_protocol.perform_comparisons(...)`.
        * Call `scoring_ranking.record_comparisons_and_update_scores(...)`, passing `db_protocol.session()`.
        * Call `scoring_ranking.check_score_stability(...)`.
        * Update internal CJ batch status via `db_protocol.update_cj_batch_status(...)`.
    * **Step 4: Get Final Rankings:**
        * Call `scoring_ranking.get_essay_rankings(...)` via `db_protocol.session()`.
    * Return `(final_rankings, internal_cj_batch_id_str)`.
    * Ensure robust error handling throughout.
2. **Helper `_ingest_single_essay`:** Implement as previously outlined.

**Phase 5 Checklist:**

* [ ] `run_cj_assessment_workflow` function implemented in `core_assessment_logic.py`.
* [ ] Workflow correctly initializes CJ batch, ingests essays (fetches content, stores in CJ DB).
* [ ] Comparison loop adapted, using protocols for DB and LLM interactions.
* [ ] `pair_generation` and `scoring_ranking` modules are correctly invoked.
* [ ] Final rankings are prepared, and results for publishing are returned.
* [ ] Consistent use of `els_essay_id` (string) for essay identification in logic.

---

### Phase 6: Implement Worker Entry Point

**Goal:** Create the Kafka consumer loop in `worker_main.py` and the message deserialization/orchestration logic in `event_processor.py`.

**Affected Files:**

* `services/cj_assessment_service/worker_main.py` (updated)
* `services/cj_assessment_service/event_processor.py` (updated)

**Implementation Instructions:**

1. **`worker_main.py`:**
    * Adapt from `spell_checker_service/worker_main.py`.
    * Initialize Dishka `CJAssessmentServiceProvider`.
    * Set up Kafka consumer (using `aiokafka`) to listen to `settings.CJ_ASSESSMENT_REQUEST_TOPIC` (which will be `huleedu.els.cj_assessment.requested.v1`).
    * Manage consumer lifecycle (start, stop, graceful shutdown, signal handling).
    * In the consumption loop, pass the `ConsumerRecord` and injected dependencies to `event_processor.process_single_message`.
    * Handle message commit logic (manual commits after successful processing).
    * Start Prometheus metrics server.
2. **`event_processor.py`:**
    * Define `async def process_single_message(msg: ConsumerRecord, core_logic_func: Callable, event_publisher: CJEventPublisherProtocol, # Add other DI deps if core_logic_func needs more directly ...)`
    * Deserialize `msg.value` into `EventEnvelope[ELS_CJAssessmentRequestV1]`.
    * Validate the deserialized event.
    * Extract `event_data: ELS_CJAssessmentRequestV1`.
    * Call `core_assessment_logic.run_cj_assessment_workflow(event_data, db_protocol, content_protocol, llm_protocol, settings)`. (These protocols would be passed into `process_single_message` from `worker_main` after being resolved by Dishka).
    * Receive `(rankings, cj_job_id_ref)` from the core logic.
    * Construct `CJAssessmentCompletedV1` event payload (to be defined in `common_core`).
    * Use `event_publisher.publish_assessment_completed(...)` to send the result.
    * Implement error handling: if `run_cj_assessment_workflow` raises an exception, catch it, log appropriately, and potentially publish a `CJAssessmentFailedV1` event.
    * Return `True` for commit if processing (including publishing results) was successful, `False` otherwise (or handle for DLQ).

**Phase 6 Checklist:**

* [ ] `worker_main.py` sets up Kafka consumer, DI, and metrics server.
* [ ] Message consumption loop correctly calls `event_processor`.
* [ ] `event_processor.py` deserializes `ELS_CJAssessmentRequestV1`.
* [ ] `event_processor.py` calls `core_assessment_logic.run_cj_assessment_workflow` with DI-provided protocols.
* [ ] Result event (`CJAssessmentCompletedV1`) is published.
* [ ] Error handling and message commit logic are in place.

---

### Phase 7: Testing, Documentation, and Finalization

**Goal:** Ensure the service is robust, well-documented, and fully integrated.

**Tasks:**

1. **Unit Tests:** Write unit tests for:
    * `core_assessment_logic.py` (mocking protocols).
    * `pair_generation.py` and `scoring_ranking.py` (if not already covered by prototype tests, adapt them).
    * `event_processor.py` (mocking core logic and publisher).
    * Protocol implementations (e.g., `llm_interaction_impl.py` mocking `aiohttp` calls).
2. **Integration Tests:** (May require more setup or be part of E2E later)
    * Test interaction with a real (or test-containerized) database.
    * Test Kafka message consumption and production.
3. **`README.md`:** Document the service's purpose, architecture, configuration, how to run it, events consumed/produced.
4. **Code Quality:** Run `pdm run lint-all`, `pdm run typecheck-all`.
5. **Review:** Code review and architectural review.

**Phase 7 Checklist:**

* [ ] Unit tests written and passing for key components.
* [ ] `README.md` for `cj_assessment_service` is complete and accurate.
* [ ] Code quality checks (linting, type checking) pass.
* [ ] Service successfully builds with Docker and runs.

---

This ticket provides a detailed plan for refactoring your CJ assessment prototype. Remember to tackle one phase at a time and ensure checkpoints are met before proceeding.

---

## Task Ticket 2: Accommodate Core HuleEdu Services for CJ Assessment Service Integration

**Ticket ID:** `HULEEDU_CORE_CJ_INTEGRATE_001`
**Title:** Update Core Services (BOS, ELS) to Integrate CJ Assessment Service
**Sprint Goal:** Modify existing Batch Orchestrator Service (BOS) and Essay Lifecycle Service (ELS) to incorporate the new Comparative Judgment (CJ) Assessment pipeline, including defining necessary event contracts and updating service logic.

**Description:**
With the new `cj_assessment_service` being developed, the core HuleEdu services (primarily BOS and ELS) need to be updated to:

1. Define the command and event contracts required to request and receive results from CJ assessment.
2. Allow BOS to manage the CJ assessment pipeline as part of a batch's overall processing lifecycle.
3. Enable ELS to receive commands from BOS for CJ, dispatch requests to the `cj_assessment_service`, and handle its results.

---

### Phase 1: Define New `common_core` Event Contracts

**Goal:** Create all necessary Pydantic models for commands and events related to CJ assessment, and update `common_core` enums and topic mappings.

**Affected Files:**

* `common_core/src/common_core/batch_service_models.py` (updated)
* `common_core/src/common_core/events/cj_assessment_events.py` (new)
* `common_core/src/common_core/enums.py` (updated)
* `common_core/src/common_core/__init__.py` (updated for new models)

**Implementation Instructions:**

1. **Command Event (BOS -> ELS): `BatchServiceCJAssessmentInitiateCommandDataV1`**
    * Location: `common_core/src/common_core/batch_service_models.py`
    * Purpose: BOS instructs ELS to start the CJ assessment phase for specified essays in a batch.
    * Structure (as discussed):

        ```python
        from .events.base_event_models import BaseEventData
        from .metadata_models import EssayProcessingInputRefV1, EntityReference
        from typing import List
        
        class BatchServiceCJAssessmentInitiateCommandDataV1(BaseEventData):
            # entity_ref (from BaseEventData) will be the BOS Batch ID.
            # event_name (from BaseEventData) will be ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND.value
            essays_to_process: List[EssayProcessingInputRefV1]
            language: str
            course_code: str
            # class_designation: str # Deferred (YAGNI)
            essay_instructions: str
        ```

2. **Request Event (ELS -> CJ Assessment Service): `ELS_CJAssessmentRequestV1`**
    * Location: `common_core/src/common_core/events/cj_assessment_events.py` (new file)
    * Purpose: ELS requests the CJ Assessment Service to perform CJ on a list of essays.
    * Structure (as discussed):

        ```python
        from ..metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata, EntityReference
        from .base_event_models import BaseEventData
        from ..enums import ProcessingEvent # Assuming ProcessingEvent is in common_core.enums
        from typing import List
        from pydantic import Field

        class ELS_CJAssessmentRequestV1(BaseEventData):
            event_name: ProcessingEvent = Field(default=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            system_metadata: SystemProcessingMetadata # Populated by ELS
            essays_for_cj: List[EssayProcessingInputRefV1]
            language: str
            course_code: str
            # class_designation: str # Deferred
            essay_instructions: str
        ```

3. **Result Event (CJ Assessment Service -> ELS): `CJAssessmentCompletedV1`**
    * Location: `common_core/src/common_core/events/cj_assessment_events.py`
    * Purpose: CJ Assessment Service reports the completion (success/partial success) of an assessment job.
    * Structure:

        ```python
        from ..metadata_models import SystemProcessingMetadata, EntityReference
        from .base_event_models import ProcessingUpdate # Or BaseEventData + explicit system_metadata
        from ..enums import ProcessingEvent # Example status might come from a CJ-specific status enum or a generic one
        from typing import List, Dict, Any
        from pydantic import Field

        class CJAssessmentCompletedV1(ProcessingUpdate): # Using ProcessingUpdate for status and system_metadata
            event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
            # entity_ref (from BaseEventData) is the BOS Batch ID this result pertains to.
            # status (from ProcessingUpdate) indicates outcome (e.g. a general "COMPLETED_SUCCESSFULLY" or specific CJ success status).
            # system_metadata (from ProcessingUpdate) populated by CJ Assessment Service.
            
            cj_assessment_job_id: str # The internal ID from CJ_BatchUpload, for detailed log/result lookup
            rankings: List[Dict[str, Any]] # The consumer-friendly ranking data
            # Example: [{"els_essay_id": "uuid1", "rank": 1, "score": 0.75}, ...]
        ```

4. **Failure Event (CJ Assessment Service -> ELS): `CJAssessmentFailedV1`** (Optional, but good practice)
    * Location: `common_core/src/common_core/events/cj_assessment_events.py`
    * Purpose: CJ Assessment Service reports a failure in processing an assessment job.
    * Structure (similar to `ProcessingUpdate`, focusing on error details):

        ```python
        # ... imports ...
        class CJAssessmentFailedV1(ProcessingUpdate):
            event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_FAILED)
            # entity_ref (from BaseEventData) is the BOS Batch ID.
            # status (from ProcessingUpdate) indicates failure.
            # system_metadata (from ProcessingUpdate) should contain detailed error_info.
            cj_assessment_job_id: str # Internal CJ Job ID
        ```

5. **Update `common_core/enums.py`:**
    * Add to `ProcessingEvent`:

        ```python
        BATCH_CJ_ASSESSMENT_INITIATE_COMMAND = "batch.cj_assessment.initiate.command"
        ELS_CJ_ASSESSMENT_REQUESTED = "els.cj_assessment.requested"
        CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"
        CJ_ASSESSMENT_FAILED = "cj_assessment.failed"
        ```

    * Add to `_TOPIC_MAPPING`:

        ```python
        ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND: "huleedu.batch.cj_assessment.initiate.command.v1",
        ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED: "huleedu.els.cj_assessment.requested.v1",
        ProcessingEvent.CJ_ASSESSMENT_COMPLETED: "huleedu.cj_assessment.completed.v1",
        ProcessingEvent.CJ_ASSESSMENT_FAILED: "huleedu.cj_assessment.failed.v1",
        ```

6. **Update `common_core/__init__.py`:** Add new models to `__all__` and ensure `model_rebuild()` is called for them.

**Phase 1 Checklist: ✅ COMPLETED**

* [x] `BatchServiceCJAssessmentInitiateCommandDataV1` model defined in `batch_service_models.py`.
* [x] `ELS_CJAssessmentRequestV1`, `CJAssessmentCompletedV1`, `CJAssessmentFailedV1` models defined in `cj_assessment_events.py`.
* [x] All new `ProcessingEvent` members added to the enum.
* [x] All new topic names added to `_TOPIC_MAPPING`.
* [x] `common_core/__init__.py` updated.
* [x] All new models successfully rebuild.

**Implementation Status:** Phase 1 is COMPLETE. The common core event contracts have been fully implemented:
- Created `cj_assessment_events.py` with all required event models
- Added `BATCH_CJ_ASSESSMENT_INITIATE_COMMAND`, `ELS_CJ_ASSESSMENT_REQUESTED`, `CJ_ASSESSMENT_COMPLETED`, `CJ_ASSESSMENT_FAILED` to ProcessingEvent enum
- Updated topic mappings for all new events
- Updated common_core exports and model rebuilds
- All new event models pass type checking and can be instantiated correctly
- CJ command model `BatchServiceCJAssessmentInitiateCommandDataV1` already exists in `batch_service_models.py`

---

### Phase 2: Update Batch Orchestrator Service (BOS)

**Goal:** Enable BOS to manage and initiate the CJ Assessment pipeline, and react to its completion/failure.

**Affected Files:**

* `common_core/pipeline_models.py` (updated)
* `services/batch_orchestrator_service/protocols.py` (potentially updated)
* `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py` (updated)
* `services/batch_orchestrator_service/kafka_consumer.py` (updated)
* `services/batch_orchestrator_service/config.py` (add new topic name from settings)

**Implementation Instructions:**

1. **Update `common_core/pipeline_models.py`:**
    * Add `cj_assessment: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)` to the `ProcessingPipelineState` model.
2. **Update BOS `config.py`:** Add setting for `CJ_ASSESSMENT_COMPLETED_TOPIC` and `CJ_ASSESSMENT_FAILED_TOPIC`.
3. **Update BOS `BatchProcessingServiceImpl` (`implementations/batch_processing_service_impl.py`):**
    * Modify logic that decides which pipeline to run next. If a batch requests CJ assessment:
        * Check if dependencies (e.g., spellcheck pipeline status is `COMPLETED_SUCCESSFULLY` in `ProcessingPipelineState`) are met.
        * If dependencies met, construct and publish the `BatchServiceCJAssessmentInitiateCommandDataV1` event to ELS.
        * The data for this command (list of essays, language, course code, instructions) would be retrieved from the `BatchRepositoryProtocol` (where it was stored during initial batch registration).
        * Update the `ProcessingPipelineState.cj_assessment.status` to `PipelineExecutionStatus.DISPATCH_INITIATED` (or similar).
4. **Update BOS `KafkaConsumer` (`kafka_consumer.py`):**
    * Add handlers for `CJAssessmentCompletedV1` and `CJAssessmentFailedV1` events (consumed from Kafka, published by ELS after it processes results from CJ Assessment Service).
    * On `CJAssessmentCompletedV1`: Update `ProcessingPipelineState.cj_assessment.status` to `COMPLETED_SUCCESSFULLY` (or `COMPLETED_WITH_PARTIAL_SUCCESS`), update `essay_counts`, `completed_at`.
    * On `CJAssessmentFailedV1`: Update `ProcessingPipelineState.cj_assessment.status` to `FAILED`, store `error_info`.
    * After processing these events, BOS logic should determine if further pipelines need to be initiated for the batch or if the batch processing is complete.
    * Ensure the consumer subscribes to these new topics.

**Phase 2 Checklist:**

* [ ] `ProcessingPipelineState` in `common_core` updated for `cj_assessment`.
* [ ] BOS can construct and publish `BatchServiceCJAssessmentInitiateCommandDataV1` to ELS when CJ pipeline is due.
* [ ] BOS updates its `ProcessingPipelineState` for `cj_assessment` upon initiation.
* [ ] BOS `KafkaConsumer` subscribes to and handles `CJAssessmentCompletedV1` and `CJAssessmentFailedV1` events.
* [ ] BOS updates `ProcessingPipelineState` for `cj_assessment` upon completion/failure.

---

### Phase 3: Update Essay Lifecycle Service (ELS)

**Goal:** Enable ELS to process CJ assessment commands from BOS, dispatch requests to the `cj_assessment_service`, and relay results back to BOS.

**Affected Files:**

* `services/essay_lifecycle_service/protocols.py` (updated)
* `services/essay_lifecycle_service/implementations/batch_command_handler_impl.py` (updated)
* `services/essay_lifecycle_service/implementations/service_request_dispatcher.py` (updated)
* `services/essay_lifecycle_service/batch_command_handlers.py` (router, updated)
* `services/essay_lifecycle_service/state_store.py` (potentially new `EssayStatus`)
* `services/essay_lifecycle_service/worker_main.py` (updated consumer topics)
* `services/essay_lifecycle_service/config.py` (add new topic names from settings)
* `common_core/enums.py` (potentially new `EssayStatus`)

**Implementation Instructions:**

1. **New `EssayStatus` (Optional but Recommended):**
    * In `common_core/enums.py`, add to `EssayStatus`: `AWAITING_CJ_ASSESSMENT`, `CJ_ASSESSMENT_IN_PROGRESS`, `CJ_ASSESSMENT_COMPLETED`, `CJ_ASSESSMENT_FAILED_INDIVIDUAL`.
2. **Update ELS `config.py`:** Add settings for topics: `BATCH_CJ_ASSESSMENT_INITIATE_COMMAND_TOPIC`, `ELS_CJ_ASSESSMENT_REQUEST_TOPIC`, `CJ_ASSESSMENT_COMPLETED_TOPIC`, `CJ_ASSESSMENT_FAILED_TOPIC`.
3. **Update ELS `protocols.py`:**
    * Add `process_initiate_cj_assessment_command` to `BatchCommandHandler` protocol.
    * Add `dispatch_cj_assessment_requests` to `SpecializedServiceRequestDispatcher` protocol (or a more generic dispatch method if preferred). This method would take the necessary data (list of essays, context) to build `ELS_CJAssessmentRequestV1`.
4. **Update ELS `implementations/batch_command_handler_impl.py`:**
    * Implement `process_initiate_cj_assessment_command`:
        * Receives `BatchServiceCJAssessmentInitiateCommandDataV1`.
        * For each essay in `command_data.essays_to_process`:
            * Update its state in `EssayStateStore` to `EssayStatus.AWAITING_CJ_ASSESSMENT`.
        * Call the new method on `SpecializedServiceRequestDispatcher` to dispatch the `ELS_CJAssessmentRequestV1` event to the CJ Assessment Service.
5. **Update ELS `implementations/service_request_dispatcher.py`:**
    * Implement `dispatch_cj_assessment_requests`:
        * Constructs the `ELS_CJAssessmentRequestV1` payload using data from the BOS command.
        * Publishes this event to `settings.ELS_CJ_ASSESSMENT_REQUEST_TOPIC` using the `EventPublisher` (which uses `AIOKafkaProducer`).
6. **Update ELS Event Router (`batch_command_handlers.py`):**
    * Add a route for `topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND)` to call the new handler method.
    * Add routes for `topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)` and `topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)` to handle results from the CJ Assessment Service.
        * These handlers will update individual `EssayState` records.
        * Aggregate results for the batch.
        * When all essays in the batch for the CJ phase are processed, publish an appropriate event to BOS (e.g., `BatchPhaseConcluded` or a new specific event like `BatchCJAssessmentPhaseCompleted`).
7. **Update ELS `worker_main.py`:**
    * Ensure the Kafka consumer subscribes to `BATCH_CJ_ASSESSMENT_INITIATE_COMMAND_TOPIC`, `CJ_ASSESSMENT_COMPLETED_TOPIC`, and `CJ_ASSESSMENT_FAILED_TOPIC`.

**Phase 3 Checklist:**

* [ ] New `EssayStatus` enums (if any) defined and used in ELS.
* [ ] ELS `protocols.py` updated for CJ command and dispatch.
* [ ] `batch_command_handler_impl.py` implements logic to handle CJ command from BOS.
* [ ] `service_request_dispatcher.py` implements logic to publish `ELS_CJAssessmentRequestV1`.
* [ ] ELS event router handles new command and result events.
* [ ] ELS worker subscribes to new topics.
* [ ] ELS correctly updates essay states and reports batch phase completion for CJ to BOS.

---

### Phase 4: Integration Testing and Validation

**Goal:** Ensure the entire CJ assessment pipeline, from BOS initiation to CJ service processing and results reporting back to BOS, functions correctly.

**Tasks:**

1. **Develop Test Scenarios:**
    * Batch with essays successfully processed by CJ.
    * Batch where CJ processing fails for some/all essays.
    * Dependencies (spellcheck before CJ) are correctly handled by BOS.
2. **Manual or Automated E2E Testing:**
    * Trigger a batch processing request that includes the CJ assessment pipeline.
    * Monitor Kafka topics for correct event flow (`BatchServiceCJAssessmentInitiateCommandDataV1` -> `ELS_CJAssessmentRequestV1` -> `CJAssessmentCompletedV1` -> ELS internal aggregation -> ELS event to BOS).
    * Verify database states in BOS (ProcessingPipelineState), ELS (EssayState), and `cj_assessment_service` (CJBatchUpload, ProcessedEssay, ComparisonPair).
    * Check service logs for correct processing and error handling.
3. **Refine and Debug:** Address any issues found during testing.

**Phase 4 Checklist:**

* [ ] End-to-end flow for CJ assessment (BOS -> ELS -> CJ Service -> ELS -> BOS) tested and working.
* [ ] Correct events are published and consumed by each service.
* [ ] Pipeline statuses in BOS and essay states in ELS are updated correctly.
* [ ] CJ Assessment Service processes requests and stores results as expected.
* [ ] Error scenarios are handled gracefully.

---

## 📋 **NEXT SESSION STARTING POINTS**

### **Immediate Next Steps:**

1. **Continue with Ticket 1, Phase 2:** Data Models and Protocol Implementation
   - Adapt database models from prototype (`models_db.py`, `enums_db.py`) 
   - Create concrete API models for internal data structures
   - Update existing prototype's `models_api.py` for string-based essay IDs

2. **Continue with Ticket 1, Phase 3:** Protocol Implementation
   - Implement concrete classes for all defined protocols
   - Set up database schema and async session management
   - Create content client for fetching spellchecked text

### **Current State Summary:**

✅ **Architecture Foundation:** All foundational components are in place and working  
✅ **Event Contracts:** Complete event flow definitions from ELS → CJ Service → ELS  
✅ **Service Structure:** CJ assessment service is scaffolded and builds successfully  
🟡 **Implementation Ready:** All prerequisites complete for actual business logic implementation  

### **Key Files Created/Modified in This Session:**

- `common_core/src/common_core/events/cj_assessment_events.py` - CJ event models
- `common_core/src/common_core/enums.py` - Updated with CJ events and topics  
- `services/cj_assessment_service/` - Complete service structure
- `docker-compose.yml` - CJ service integration
- Fixed linter error in `cj_essay_assessment/implementations/anthropic_provider_impl.py`

**Ready to continue with business logic implementation in next session.**
