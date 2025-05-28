# HuleEdu Processing Pipeline: Master Product Requirements Document

**Version:** 2.0
**Date:** May 27, 2025
**Status:** Comprehensive Draft

## 1. Introduction & Overview 🎯

This document outlines the comprehensive requirements and architectural design for the HuleEdu Processing Pipeline. The primary goal is to establish a robust, scalable, extensible, and maintainable system for processing essays through various analytical and feedback stages. This system is built upon a microservice architecture, leveraging an event-driven approach with asynchronous communication via Kafka. It mandates clear, type-safe contracts using Pydantic models for data integrity and `typing.Protocol` for defining behavioral contracts of internal service components.

The architecture emphasizes Separation of Concerns (SoC) and Domain-Driven Design (DDD) principles, leading to modular services that are independently deployable and maintainable. This modularity extends to the internal structure of each service, promoting small, focused code modules and clear behavioral contracts defined in dedicated `protocols.py` files. Dependency management and inversion will be facilitated by the Dishka DI container to enhance testability and flexibility.

We will explicitly define the data models for events at each stage, adhering to a "thin event" philosophy where events signal occurrences and carry essential, curated context rather than large data blobs. This PRD serves as a foundational guide for developing, maintaining, and extending the core processing capabilities of the HuleEdu platform, providing strong guardrails for both human and AI-assisted development.

---

## 2. Goals & Objectives 🌟

* **Modularity & Maintainability:** Decompose the processing workflow into distinct, autonomous microservices, and further into small, focused internal code modules (aspirational target <300-400 lines for primary logic units, <100 char line length). This ensures ease of understanding, modification, and extension.
* **Scalability:** Enable independent scaling of individual processing services based on demand to handle varying loads efficiently.
* **Extensibility:** Design a system that allows for the straightforward addition of new processing pipelines or steps in the future with minimal impact on unrelated modules, facilitated by clear contracts and protocol-based dependencies.
* **Robustness & Reliability:** Ensure reliable event processing through well-defined error handling paths (foundational), data integrity via explicit contracts, and fault isolation between services.
* **Comprehensive Type Safety:** Leverage Pydantic for all data contracts (event payloads, API DTOs, configurations) and `typing.Protocol` with MyPy for behavioral contracts to ensure end-to-end type safety and early error detection.
* **Asynchronous & Decoupled Processing:** Utilize an event-driven architecture with Kafka for loose coupling between services and improved system responsiveness.
* **Testability:** Design components to depend on protocol-defined abstractions, managed via Dishka DI, to allow for easy mocking, isolated unit testing, and comprehensive test coverage.
* **Traceability & Observability:** Establish clear mechanisms for tracing an essay's or batch's journey through the pipelines (via `correlation_id`) and lay the foundation for a comprehensive observability stack.
* **Developer Experience & AI Guardrails:** Provide clear, explicit contracts (data and behavioral) to enhance developer productivity and serve as strong guardrails for AI-assisted code generation, minimizing ambiguity and "AI slop."

---

## 3. Core Architectural Principles 🏗️

* **Domain-Driven Design (DDD):** Each microservice aligns with a specific bounded context (e.g., Batch Orchestration, Essay Lifecycle Management, Spell Checking).
* **Separation of Concerns (SoC):**
  * **Inter-Service:** Clear, distinct responsibilities for Batch Service (BS), Essay Lifecycle Service (ELS), and Specialized Services (SS).
  * **Intra-Service:** Within each service, responsibilities such as API handling, event consumption, event production, core business logic, data access, and external client interactions are separated into distinct, focused modules with clear interfaces.
* **Event-Driven Architecture (EDA):** Asynchronous communication via Kafka is the primary inter-service collaboration method.
* **Thin Events:** Events primarily signal occurrences and carry identifiers and essential, curated context. Large data objects (like full essay texts) are referenced via `StorageReferenceMetadata`.
* **Explicit Contracts:**
  * **Data Contracts:** All event data payloads, API DTOs, and configurations are defined by specific, versioned Pydantic models residing in `common_core`.
  * **Behavioral Contracts:** Key internal component interfaces within services (e.g., repositories, service clients, core logic units) are defined by `typing.Protocol` located in per-service `protocols.py` files.
* **`EventEnvelope` Standard:** All events transmitted over Kafka are wrapped in a standard `EventEnvelope` providing common metadata (`event_id`, `event_type`, `source_service`, `correlation_id`, etc.).
* **Dependency Inversion & Management:** Services will utilize `typing.Protocol` for internal abstractions and **Dishka** as the Dependency Injection container to manage the provision of concrete implementations. This promotes loose coupling, high testability, and flexible component swapping.
* **Small, Focused Modules & Functions:** Adherence to keeping functions, classes, and files concise (target <300-400 lines for primary logic units) to improve readability, testability, and reduce cognitive load. Code line length should not exceed 100 characters.

---

## 4. Key Services Involved 🛠️

* **Batch Service (BS):** The primary orchestrator of batch processing. Manages `ProcessingPipelineState` and initiates pipeline phases for entire batches.
* **Essay Lifecycle Service (ELS):** Manages the state and lifecycle of individual essays. Consumes batch phase initiation commands from BS. Dispatches individual essay processing requests to Specialized Services. Consumes results from Specialized Services, updates essay states, and notifies BS of these updates.
* **Content Service:** A dedicated microservice responsible for storing and retrieving all textual content and binary artifacts (e.g., original essays, corrected texts, NLP JSON, AI feedback documents). Accessed via a RESTful API.
* **Specialized Services (SS):** Perform specific, focused processing tasks on individual essays or batches. Examples:
  * **SpellChecker Service:** Performs spell checking.
  * **NLP Service:** Generates linguistic metrics and features.
  * **AI Feedback Service:** Generates AI-driven feedback and editor revisions.
  * **CJ Assessment Service:** Performs comparative judgment on essays within a batch.
* **Kafka:** The distributed event streaming platform serving as the event bus for all asynchronous inter-service communication.
* **Supporting Infrastructure (Conceptual):**
  * **API Gateway:** (Future) Single entry point for external API requests.
  * **Observability Stack:** (Future) Tools for distributed tracing, metrics, and centralized logging.

---

## 5. Detailed Service & Module Structure (Enabling Modularity & Small Files) 🧩

To achieve the goals of small, focused files and maintainable code units, each service will adopt an internal structure that promotes delegation, separation of concerns, and clearly defined behavioral contracts managed by Dishka DI. `protocols.py` files within each service will define these internal behavioral contracts.

```plaintext
huledu-reboot/
├── common_core/
│   └── src/common_core/
│       ├── __init__.py                     (~60-120 LoC - exports)
│       ├── enums.py                        (~200-350 LoC - comprehensive enums for events, statuses, etc.)
│       ├── metadata_models.py              (~200-300 LoC - EntityRef, SystemProcessingMeta, EssayProcessingInputRef, AIFeedbackMeta, etc.)
│       ├── pipeline_models.py              (~80-150 LoC - ProcessingPipelineState & components)
│       │
│       ├── batch_service_models.py         (~50-150 LoC per command model; file holds Pydantic models for commands FROM BatchService to ELS)
│       ├── essay_service_models.py         (~50-150 LoC per request model; file holds Pydantic models for requests FROM ELS to Specialized Services)
│       │
│       └── events/                         (Specific result data models from SS, and common event bases)
│           ├── __init__.py                 (~40-80 LoC - exports)
│           ├── base_event_models.py        (~60-100 LoC - BaseEventData, ProcessingUpdate, EventTracker)
│           ├── envelope.py                 (~30-50 LoC - EventEnvelope)
│           ├── common_pipeline_events.py   (~60-120 LoC - Optional: Base models for shared BS->ELS commands or ELS->SS requests if inputs are truly identical)
│           ├── spellcheck_events.py        (~40-80 LoC - e.g., EssaySpellcheckConcludedDataV1)
│           ├── nlp_events.py               (~40-80 LoC - e.g., EssayNLPConcludedDataV1)
│           ├── ai_feedback_events.py       (~60-120 LoC - e.g., AIFeedbackInputDataV1, EssayAIFeedbackConcludedDataV1)
│           └── cj_assessment_events.py     (~60-120 LoC - e.g., CJAssessmentOutputMetadata, CJAssessmentBatchConcludedDataV1)
│
├── services/
│   ├── batch_service/  (Orchestrates batch pipeline progression)
│   │   ├── __init__.py
│   │   ├── app.py                        (If BS has an API: Quart app, routes, DI container setup with Dishka, startup/shutdown. ~150-300 LoC)
│   │   ├── orchestrator.py               (Contains main orchestration logic `check_and_initiate_next_pipeline_phase`. Depends on `BatchRepositoryProtocol`, `BatchEventPublisherProtocol`, `BatchStateManagerProtocol`. ~200-350 LoC)
│   │   │   └── Delegates to pipeline-specific internal helper functions/classes for preparing initiation command data.
│   │   ├── pipeline_initiators/          (Optional sub-package if initiation logic per pipeline is complex)
│   │   │   ├── __init__.py
│   │   │   ├── spellcheck_initiator.py   (~80-120 LoC - Prepares `BatchServiceSpellcheckInitiateCommandDataV1`)
│   │   │   └── (similar files for nlp, ai_feedback, cj initiators)
│   │   ├── event_publisher.py            (Implements `BatchEventPublisherProtocol`. Constructs & publishes BS-specific events. ~80-150 LoC)
│   │   ├── state_manager.py              (Implements `BatchStateManagerProtocol`. Manages `ProcessingPipelineState` updates via repository. ~150-300 LoC)
│   │   ├── repository.py                 (Implements `BatchRepositoryProtocol` for DB access. ~150-350 LoC)
│   │   ├── protocols.py                  (Defines `BatchRepositoryProtocol`, `BatchEventPublisherProtocol`, `BatchStateManagerProtocol`. ~60-150 LoC)
│   │   └── config.py                     (Pydantic settings. ~30-50 LoC)
│   │
│   ├── essay_lifecycle_service/ (Manages essay states, dispatches to SS, collects results)
│   │   ├── __init__.py
│   │   ├── worker_main.py                (Kafka consumer loop entry point; DI setup with Dishka. ~50-100 LoC)
│   │   ├── event_router.py               (Consumes from Kafka, deserializes `EventEnvelope`, routes to specific handlers based on `event_type`. ~100-200 LoC)
│   │   │
│   │   ├── bs_command_handlers/          (Directory for handlers of commands from BatchService)
│   │   │   ├── __init__.py
│   │   │   ├── spellcheck_initiation_handler.py  (Handles `BatchServiceSpellcheckInitiateCommandDataV1`. Depends on `RequestDispatcherProtocol`, `EssayRepositoryProtocol`, ELS `EventPublisherProtocol`. ~100-200 LoC)
│   │   │   └── ... (other pipeline initiation handlers, each in its own file)
│   │   │
│   │   ├── ss_result_handlers/           (Directory for handlers of results from SpecializedServices)
│   │   │   ├── __init__.py
│   │   │   ├── spellcheck_conclusion_handler.py (Handles `EssaySpellcheckConcludedV1`. Depends on `EssayRepositoryProtocol`, ELS `EventPublisherProtocol`. ~80-150 LoC)
│   │   │   └── ... (other result handlers, each in its own file)
│   │   │
│   │   ├── request_dispatcher.py         (Implements `RequestDispatcherProtocol`. Methods to build & publish specific `EssayLifecycle...RequestV1` to SSs. ~200-350 LoC, with small methods per SS type)
│   │   ├── event_publisher.py            (Implements ELS-specific `EventPublisherProtocol` for `ESSAY_LIFECYCLE_STATE_UPDATED_V1`. ~50-100 LoC)
│   │   ├── repository.py                 (Implements `EssayRepositoryProtocol` for ProcessedEssay DB access. ~150-350 LoC)
│   │   ├── protocols.py                  (Defines `EssayRepositoryProtocol`, `RequestDispatcherProtocol`, `ELSPipelineEventHandlerProtocol` (for handler classes), ELS `EventPublisherProtocol`. ~100-200 LoC)
│   │   └── config.py                     (Pydantic settings. ~30-50 LoC)
│   │
│   └── specialized_services/
│       └── spell_checker_service/        (Example Specialized Service)
│           ├── __init__.py
│           ├── worker_main.py            (Kafka consumer loop, DI setup, routes to `handler.process_request`. ~80-150 LoC)
│           ├── handler.py                (Implements `SpellcheckerRequestHandlerProtocol`. Consumes `EssayLifecycleSpellcheckRequestV1`. Depends on `ContentClientProtocol`, `SpellLogicProtocol`, `EventPublisherProtocol`. ~150-250 LoC)
│           ├── core_logic.py             (Implements `SpellLogicProtocol`. Actual spellchecking. ~100-300+ LoC, further modularized if complex)
│           ├── event_publisher.py        (Implements `EventPublisherProtocol` for `EssaySpellcheckConcludedV1`. ~50-100 LoC)
│           ├── content_client.py         (Implements `ContentClientProtocol`. HTTP client for Content Service API. ~80-150 LoC)
│           ├── protocols.py              (Defines `ContentClientProtocol`, `SpellLogicProtocol`, `SpellcheckerRequestHandlerProtocol`. ~60-120 LoC)
│           └── config.py                 (Pydantic settings. ~30-50 LoC)
│
└── huleedu_service_libs/                 (Shared technical utilities)
    └── src/huleedu_service_libs/
        ├── __init__.py
        ├── kafka_client.py             (e.g., `KafkaBus` class. Could implement a base `RawEventPublisherProtocol`. ~100-200 LoC)
        ├── logging_utils.py            (~50-100 LoC)
        └── protocols.py                (e.g., Defines `RawEventPublisherProtocol`. ~20-40 LoC)
```

**Achieving Small File Sizes within this Structure:**
This structure achieves manageable file sizes by:

* **Protocol-Defined Boundaries:** Internal components (repositories, clients, logic units) interact via interfaces defined in `protocols.py`. Their dependencies are these protocols, injected by Dishka.
* **Delegation:** Main orchestrating or routing modules delegate pipeline-specific or event-specific logic to dedicated, smaller functions or classes (often organized into sub-directories like `bs_command_handlers/`).
* **Single Responsibility:** Each module and, ideally, each function/method within it, has a single, clear responsibility. Publishers publish, repositories handle data access, handlers process one event type, core logic performs algorithms.

---

## 6. Detailed Pipeline Flows & Data Models 🌊

This section details the interaction for each processing pipeline, emphasizing the Pydantic data models used in `EventEnvelope.data` and the roles of each service.

### 6.1. Common Pydantic Components

* **`common_core.metadata_models.EntityReference`**: (`entity_id`, `entity_type`, `parent_id`) - Identifies entities.
* **`common_core.metadata_models.EssayProcessingInputRefV1`**: (`essay_id`, `text_storage_id`) - Points to an essay and its text for processing.
* **`common_core.events.base_event_models.BaseEventData`**: Base for event payloads (`event_name`, `entity_ref`, `timestamp`).
* **`common_core.events.base_event_models.ProcessingUpdate`**: Extends `BaseEventData` with `status` and `system_metadata` (an instance of `common_core.metadata_models.SystemProcessingMetadata`).
* **`common_core.metadata_models.StorageReferenceMetadata`**: Carries references to stored artifacts.

### 6.2. Pipeline 1: Spell Checking

* **Purpose:** Identify and correct spelling errors.
* **Input:** Original essay text, language.
* **Output:** Corrected text, spellcheck metrics/log.

**Event Flow & Data Models:**

1. **BS Initiates Spellcheck Phase for Batch:**
    * `EventEnvelope.event_type`: `"huleedu.batchservice.spellcheck_phase.initiate.v1"`
    * `EventEnvelope.data` (Type: `BatchServiceSpellcheckInitiateCommandDataV1` from `common_core.batch_service_models`):

        ```python
        # From BaseEventData: entity_ref (Batch), event_name (BATCH_SPELLCHECK_PHASE_INITIATE)
        essays_to_process: List[EssayProcessingInputRefV1]
        language: str 
        ```

    * BS Updates `ProcessingPipelineState.spellcheck` to `DISPATCH_INITIATED`, publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.

2. **ELS Requests Spellcheck for Individual Essay:**
    * `EventEnvelope.event_type`: `"huleedu.els.spellcheck.request.v1"`
    * `EventEnvelope.data` (Type: `EssayLifecycleSpellcheckRequestV1` from `common_core.essay_service_models`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_SPELLCHECK_REQUESTED), status (AWAITING_SPELLCHECK), system_metadata
        text_storage_id: str 
        language: str
        ```

    * ELS updates essay status, publishes `ESSAY_LIFECYCLE_STATE_UPDATED_V1`.

3. **SpellChecker Service Publishes Result:**
    * `EventEnvelope.event_type`: `"huleedu.spellchecker.essay.concluded.v1"`
    * `EventEnvelope.data` (Type: `EssaySpellcheckConcludedV1` from `common_core.events.spellcheck_events`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_SPELLCHECK_RESULT_RECEIVED), status (SPELLCHECKED_SUCCESS/_FAILED), system_metadata
        original_text_storage_id: str
        storage_metadata: Optional[StorageReferenceMetadata] 
        corrections_made: Optional[int]
        ```

4. **ELS Processes Result & Updates BS:** ELS updates essay, publishes `ESSAY_LIFECYCLE_STATE_UPDATED_V1`. BS consumes, updates `ProcessingPipelineState.spellcheck`, publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.

---

### 6.3. Pipeline 2: NLP Service

* **Purpose:** Generate linguistic metrics.
* **Input:** Spell-corrected essay text, language.
* **Output:** NLP metrics artifact (JSON).

**Event Flow & Data Models:**

1. **BS Initiates NLP Phase for Batch:**
    * `EventEnvelope.event_type`: `"huleedu.batchservice.nlp_phase.initiate.v1"`
    * `EventEnvelope.data` (Type: `BatchServiceNLPInitiateCommandDataV1` from `common_core.batch_service_models` - or a shared `BatchServiceTextProcessingInitiateCommandDataV1` if inputs identical to spellcheck):

        ```python
        # From BaseEventData: entity_ref (Batch), event_name (BATCH_NLP_PHASE_INITIATE)
        essays_to_process: List[EssayProcessingInputRefV1] # text_storage_id points to corrected text
        language: str
        ```

2. **ELS Requests NLP Analysis for Individual Essay:**
    * `EventEnvelope.event_type`: `"huleedu.els.nlp.request.v1"`
    * `EventEnvelope.data` (Type: `EssayLifecycleNLPRequestV1` from `common_core.essay_service_models` - or shared `EssayLifecycleTextProcessRequestV1`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_NLP_REQUESTED), status (AWAITING_NLP), system_metadata
        text_storage_id: str # ID of spell-corrected text
        language: str
        ```

3. **NLP Service Publishes Result:**
    * `EventEnvelope.event_type`: `"huleedu.nlp.essay.concluded.v1"`
    * `EventEnvelope.data` (Type: `EssayNLPConcludedDataV1` from `common_core.events.nlp_events`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_NLP_RESULT_RECEIVED), status (NLP_COMPLETED_SUCCESS/_FAILED), system_metadata
        original_text_storage_id: str
        storage_metadata: StorageReferenceMetadata # Ref to NLP metrics JSON
        ```

4. **ELS Processes Result & Updates BS:** (Similar flow)

---

### 6.4. Pipeline 3: AI Feedback Service

* **Purpose:** Generate AI-driven feedback.
* **Input:** Spell-corrected text, batch context (course, instructions, teacher), essay context (student name), language.
* **Output:** AI feedback, `AIFeedbackMetadata`.

**Event Flow & Data Models:**

1. **BS Initiates AI Feedback Phase for Batch:**
    * `EventEnvelope.event_type`: `"huleedu.batchservice.aifeedback_phase.initiate.v1"`
    * `EventEnvelope.data` (Type: `BatchServiceAIFeedbackInitiateCommandDataV1` from `common_core.batch_service_models`):

        ```python
        # From BaseEventData: entity_ref (Batch), event_name (BATCH_AIFEEDBACK_PHASE_INITIATE)
        essays_to_process: List[EssayProcessingInputRefV1]
        course_code: str
        essay_instructions: str
        language: str
        teacher_name: Optional[str]
        class_designation: Optional[str]
        user_id_of_batch_owner: Optional[str]
        ai_specific_config: Optional[Dict[str, Any]]
        ```

2. **ELS Requests AI Feedback for Individual Essay:**
    * `EventEnvelope.event_type`: `"huleedu.els.aifeedback.request.v1"`
    * `EventEnvelope.data` (Type: `EssayLifecycleAIFeedbackRequestV1` from `common_core.essay_service_models`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_AIFEEDBACK_REQUESTED), status (AWAITING_AI_FEEDBACK), system_metadata
        processing_input: AIFeedbackInputDataV1 # Defined in common_core.events.ai_feedback_events
        ```

        Where `AIFeedbackInputDataV1` contains:

        ```python
        # text_storage_id, course_code, essay_instructions, language, teacher_name, 
        # class_designation, user_id_of_batch_owner, student_name
        ```

3. **AI Feedback Service Publishes Result:**
    * `EventEnvelope.event_type`: `"huleedu.aifeedback.essay.concluded.v1"`
    * `EventEnvelope.data` (Type: `EssayAIFeedbackConcludedDataV1` from `common_core.events.ai_feedback_events`):

        ```python
        # From ProcessingUpdate: entity_ref (Essay), event_name (ESSAY_AIFEEDBACK_RESULT_RECEIVED), status (AI_FEEDBACK_COMPLETED_SUCCESS/_FAILED), system_metadata
        original_text_storage_id: str
        ai_feedback_metadata: AIFeedbackMetadata # common_core.metadata_models
        storage_metadata: StorageReferenceMetadata
        ```

4. **ELS Processes Result & Updates BS:** (Similar flow)

---

### 6.5. Pipeline 4: CJ (Comparative Judgement) Assessment Service

* **Purpose:** Perform comparative judgment on a batch of essays.
* **Input:** Essay texts, batch context (course, instructions for prompts).
* **Output:** Batch-level ranking, individual essay CJ scores/metadata.

**Event Flow & Data Models:**

1. **BS Initiates CJ Assessment for Batch:**
    * `EventEnvelope.event_type`: `"huleedu.batchservice.cj_assessment_phase.initiate.v1"`
    * `EventEnvelope.data` (Type: `BatchServiceCJAssessmentInitiateCommandDataV1` from `common_core.batch_service_models`):

        ```python
        # From BaseEventData: entity_ref (Batch), event_name (BATCH_CJ_ASSESSMENT_PHASE_INITIATE)
        essays_for_cj: List[EssayProcessingInputRefV1]
        course_code: str
        essay_instructions: str
        language: Optional[str]
        user_id_of_batch_owner: Optional[str]
        cj_assessment_config: Optional[Dict[str, Any]]
        ```

2. **CJ Assessment Service Processes Batch & Publishes Result (to BS):**
    * `EventEnvelope.event_type`: `"huleedu.cjassessment.batch.concluded.v1"`
    * `EventEnvelope.data` (Type: `CJAssessmentBatchConcludedDataV1` from `common_core.events.cj_assessment_events`):

        ```python
        # From ProcessingUpdate: entity_ref (Batch), event_name (CJ_ASSESSMENT_BATCH_CONCLUDED), status (CJ-specific outcome string), system_metadata
        cj_output_metadata: CJAssessmentOutputMetadata # common_core.events.cj_assessment_events
        ```

3. **BS Processes CJ Result:** Updates `ProcessingPipelineState.cj_assessment`, publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`. If all pipelines done, sets batch to `COMPLETED`.

---

## 7. Key Pydantic Model Definitions (Summary)

* **Core Contracts:** `EventEnvelope`, `BaseEventData`, `ProcessingUpdate`, `EntityReference`, `SystemProcessingMetadata`, `StorageReferenceMetadata`, `EssayProcessingInputRefV1`.
* **Pipeline State:** `ProcessingPipelineState`, `PipelineStateDetail`, `EssayProcessingCounts`.
* **Specific Event Data Models:** As detailed in Section 6 for each pipeline command and result (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`, `EssayLifecycleSpellcheckRequestV1`, `EssaySpellcheckConcludedDataV1`, etc.).
* **Specific Output Metadata:** `AIFeedbackMetadata`, `CJAssessmentOutputMetadata`.

---

## 8. `typing.Protocol` Integration Strategy & Benefits 📜

To further enhance internal service design, testability, and provide clear behavioral contracts, especially when working with LLM-assisted development, `typing.Protocol` will be adopted for key internal abstractions.

**Strategy:**

* Protocols will be defined in per-service `protocols.py` files.
* Key internal components like repositories, clients for other services (e.g., Content Service client), and core logic units will implement or depend on these protocols.
* Dishka DI will be used to inject concrete implementations where protocols are type-hinted.

**Target Areas for Protocols:**

* **Shared Libraries:** `EventPublisherProtocol` (for `KafkaBus`).
* **Batch Service:** `BatchRepositoryProtocol`, `BatchEventPublisherProtocol`, `BatchStateManagerProtocol`.
* **Essay Lifecycle Service:** `EssayRepositoryProtocol`, `RequestDispatcherProtocol` (for sending to SS), ELS-specific `EventPublisherProtocol`.
* **Specialized Services:** `ContentClientProtocol`, `SpellLogicProtocol` (for Spellchecker), similar for other SS core logic.

**Benefits Specific to Protocol Adoption:**

* **Enhanced Type Safety for Behavior:** Statically verify method signatures and attributes.
* **Superior Testability:** Easily mock dependencies based on protocol contracts.
* **Clearer Internal Component Boundaries:** Explicit interfaces improve SoC within each service.
* **Stronger LLM Guardrails:** Protocols provide precise behavioral blueprints for LLMs.
* **Increased Code Readability:** Expected behaviors become explicit.

---

## 9. Dependency Injection with Dishka 💉

* **Purpose:** To manage dependencies between components within each service, promoting loose coupling and testability.
* **Mechanism:** Dishka will be configured at service startup (`app.py` or `worker_main.py`) to provide concrete implementations when a dependency (typed with a `typing.Protocol`) is required by a component (e.g., a handler needing a repository).
* **Benefits:**
  * Simplifies component wiring.
  * Makes replacing implementations straightforward (e.g., swapping a real repository with a mock for testing).
  * Enhances modularity by decoupling components from the knowledge of how their dependencies are created.

---

## 10. Non-Functional Requirements (Highlights)

* **Modularity & Code Structure:** As per Section 5, emphasizing small, focused modules interconnected via protocol-defined interfaces and managed by Dishka DI. Target <300-400 lines for core functional units, 100-char line length.
* **Testability:** High unit test coverage facilitated by DI of protocol-based mocks. Contract testing for Pydantic event models.
* **Extensibility:** Clear contracts (Pydantic for data, Protocols for behavior) and decoupled components (via DI and EDA) simplify adding new pipelines or modifying existing ones.
* **Configuration:** Services configurable via environment variables using Pydantic settings.
* **Logging:** Structured, contextual logging with `correlation_id` propagated.
* **Error Handling:** Graceful error handling within services; result events indicate success/failure. DLQ strategy for unrecoverable event processing failures is a future consideration.
* **Idempotency:** Event consumers should strive for idempotency where operations might be retried.

---

## 11. Implementation Roadmap (Conceptual - Next Sprints) 🗺️

1. **Sprint X (Focus: Protocol & DI Foundation):**
    * Define initial set of `typing.Protocol`s for core components (repositories, key service clients, event publishers) in each service (`protocols.py`).
    * Integrate Dishka into one or two pilot services for DI setup.
    * Refactor targeted existing components in these pilot services to use/implement these protocols and be managed by Dishka.
    * Update development guidelines and provide team training on Protocols & Dishka.
2. **Sprint X+1 (Focus: Pipeline Implementation - e.g., NLP):**
    * Define Pydantic event data models for the NLP pipeline in `common_core`.
    * Implement NLP pipeline logic in BS (orchestrator, state manager), ELS (command/result handlers, request dispatcher), and the new NLP Specialized Service, adhering to protocol-based internal design and using Dishka.
    * Write unit and integration tests.
3. **Subsequent Sprints:**
    * Incrementally implement remaining pipelines (AI Feedback, CJ Assessment) following the established patterns.
    * Continuously apply protocol-based design and DI to new and refactored components.
    * Begin work on foundational observability components (e.g., basic metrics).

---

## 12. Success Metrics 📊

* **Pipeline Functionality:** Successful end-to-end processing of essays through each implemented pipeline.
* **Code Quality:** Adherence to LoC targets, MyPy passing with high strictness, positive code review feedback regarding clarity and modularity.
* **Test Coverage:** High unit test coverage for internal components, facilitated by DI and protocol-based mocking. Successful contract tests for event schemas.
* **Extensibility:** Demonstrated ease of adding a new (simple) processing step or modifying an existing one.
* **Developer Velocity:** Stable or improved development speed for new features due to clearer structure and contracts.
* **LLM Effectiveness:** Higher quality and better adherence to design in LLM-generated code when provided with Pydantic models and `typing.Protocol` specifications.
* **System Stability:** Low rate of unexpected errors or cascading failures in integrated environments.

---

## 13. Future Considerations / Out of Scope for Initial Iterations 🔭

* Advanced, configurable retry mechanisms with exponential backoff for inter-service calls and event processing.
* Dead Letter Queues (DLQs) strategy and implementation for robust handling of unrecoverable event processing failures.
* Full distributed tracing implementation (e.g., OpenTelemetry) beyond `correlation_id`.
* Dynamic pipeline definition and user-configurable pipeline steps per batch.
* Advanced metrics, alerting, and a dedicated observability dashboard.
* API Gateway for managing external access to services.
* Service mesh (e.g., Istio, Linkerd) for advanced traffic management, security, and observability at scale.
