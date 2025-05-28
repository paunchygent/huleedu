## Architectural Design Blueprint: Refactoring HuleEdu for a Modular, Event-Driven Microservice Ecosystem

This document outlines the architectural design for refactoring the HuleEdu application into a distributed system of microservices. The primary goals are to achieve greater modularity, scalability, maintainability, and evolvability by leveraging domain-driven design principles, an event-driven architecture, and explicit contracts between services.

---
**1. Overarching Architectural Philosophy**

The refactored HuleEdu system will be built upon the following core architectural pillars:

* **Domain-Driven Design (DDD)**: Each microservice will be designed around a specific business domain or "bounded context," owning its data and logic. This promotes separation of concerns and clearer responsibilities.
* **Event-Driven Architecture (EDA)**: Asynchronous communication via events will be the primary mechanism for inter-service collaboration, promoting loose coupling, resilience, and responsiveness. Services will react to domain events published by other services.
* **Explicit Contracts**: All inter-service communication, whether via events or synchronous APIs, will be governed by explicit, versioned schemas. Your existing dataclasses (e.g., from `common/models/metadata_models.py`, `common/models/batch.py`) will be evolved into Pydantic models to serve as these schemas, residing in a shared common library.
* **Service Autonomy**: Each microservice should be independently deployable, scalable, and maintainable. Ideally, each service owns its own data store, or at least its own dedicated schema within a shared store during transition.
* **Evolvability by Design**: The architecture must support the addition of new features and services, and the evolution of existing ones, with minimal impact on other parts of the system. Versioning of contracts is key to this.

---
**2. Core Service Decomposition Strategy**

Based on your existing codebase and future needs, the following core microservices are envisioned. This decomposition aims to align services with distinct business capabilities:

* **Batch Orchestration Service (BS)**:
    * **Evolved from**: Core batch management functionalities currently within `server_web_app`.
    * **Owns**: The `BatchUpload` entity (from `common/models/batch.py`) and its overall lifecycle, governed by the `BatchStatus` enum (from `common/models/enums.py`).
    * **Responsibilities**:
        * Handles the creation and configuration of batches (e.g., linking to user/teacher, `course_code`, `class_designation`, `essay_instructions` from upload forms or system settings).
        * Orchestrates the high-level *processing phases* that a batch and its constituent essays go through (e.g., Spell Check Phase, NLP Metrics Phase, AI Feedback Pipeline, CJ Assessment Phase).
        * Publishes batch-level *command events* to initiate these phases.
        * Consumes summary or lifecycle events related to individual essays to track the aggregate progress of a batch through its current phase.
        * Manages the overall `BatchUpload.status` and the detailed `ProcessingPipelineState` (stored in `BatchUpload.processing_metadata`).
        * Acts as a primary source for batch-level aggregated data for analytics or UI.
    * **Key Interaction**: It does *not* directly manage individual essays but tells an Essay Lifecycle Service (or equivalent) which essays in a batch need to enter a new processing phase.

* **Essay Lifecycle Service (ELS)**:
    * **Conceptual Service**: This might initially be a tightly coupled logical component within the Batch Orchestrator Service or evolve into a fully separate microservice.
    * **Owns**: The `ProcessedEssay` entity (from `common/models/batch.py`) and its detailed, fine-grained lifecycle status, governed by an extended `EssayStatus` enum (from `common/models/enums.py`).
    * **Responsibilities**:
        * Manages the canonical record for each essay, including references to its various text versions (original, spell-checked, AI-revised) and links to all associated processing artifacts (NLP metrics, AI feedback details, CJ scores).
        * Consumes batch-level command events from the Batch Orchestrator Service (e.g., `INITIATE_SPELLCHECK_FOR_BATCH_V1`).
        * For each relevant essay, updates its `ProcessedEssay.status` (e.g., to `EssayStatus.AWAITING_SPELLCHECK`) and publishes essay-specific *command events* to the appropriate Specialized Processing Service (e.g., `REQUEST_SPELLCHECK_FOR_ESSAY_V1`).
        * Consumes result events from Specialized Processing Services (e.g., `ESSAY_SPELLCHECK_CONCLUDED_V1`).
        * Updates its `ProcessedEssay.status` accordingly (e.g., to `EssayStatus.SPELLCHECKED`) and stores resulting artifact references.
        * Publishes general `ESSAY_LIFECYCLE_STATE_UPDATED_V1` events, which the Batch Orchestrator Service consumes to track batch progress.

* **Specialized Processing Services (SS)**:
    * **SpellChecker Service**: Performs spell checking. Consumes `REQUEST_SPELLCHECK_FOR_ESSAY_V1`, publishes `ESSAY_SPELLCHECK_CONCLUDED_V1`. (Inspired by `src/cj_essay_assessment/spell_checker/spell_check_pipeline.py`).
    * **NLP Service**: Generates linguistic metrics and features. Consumes `REQUEST_NLP_FOR_ESSAY_V1`, publishes `ESSAY_NLP_CONCLUDED_V1`. (Inspired by `src/cj_essay_assessment/nlp_analyzer.py`).
    * **AI Feedback Service**: Generates AI-driven feedback and editor revisions. Evolves from `ai_feedback_svenska`. Consumes `REQUEST_AI_FEEDBACK_FOR_ESSAY_V1`, publishes `ESSAY_AI_FEEDBACK_CONCLUDED_V1`.
    * **CJ Assessment Service**: Performs comparative judgment. Evolves from `cj_essay_assessment`. Consumes `INITIATE_CJ_ASSESSMENT_FOR_BATCH_V1`, manages its internal batch processing using `cj_essay_assessment.db.models_db.BatchStatusEnum`, and publishes `CJ_ASSESSMENT_CONCLUDED_V1` (for the batch).
    * **Grammar Service (Planned/Prototyped)**: Would function similarly, consuming requests and publishing results for grammar analysis.

* **Supporting Services (Mentioned for Context, based on roadmap and common needs):**
    * **User/Auth Service**: Manages user identity and authentication. Provides `user_id` which BS uses to derive `teacher_name`.
    * **File Upload Service/Ingestion Point**: Handles initial essay file uploads, extracts text, and likely initiates the creation of `BatchUpload` and `ProcessedEssay` records via events/commands to BS and ELS. It would be responsible for creating the initial `storage_id` for raw content.
    * **Storage Access Service**: A thin service or library component that abstracts direct interaction with the physical storage backend (e.g., S3, local disk). It resolves abstract storage references/URNs to actual URLs and manages access permissions.
    * **Notification/WebSocket Service**: Consumes various events (especially `BATCH_PIPELINE_PROGRESS_UPDATED_V1` from BS) and pushes real-time updates to connected UI clients.
    * **Analytics Service (Future)**: Would be a primary consumer of many events to build aggregated views and derive insights.

**Rationale for Batch/Essay Service Separation (Logical or Physical):**
Separating the concerns of batch-level orchestration (BS) from individual essay lifecycle management (ELS) leads to:
* **Clearer Responsibilities**: BS focuses on "what happens to the batch as a whole and in what major sequence?" ELS focuses on "what is the precise current state of this essay and what does it need next?"
* **Independent Scalability**: If essay state updates or individual processing steps become a bottleneck, ELS can be scaled independently. If batch initiation or aggregation is the bottleneck, BS can be scaled.
* **Simplified State Machines**: Each service manages a more focused state machine relevant to its primary entity (`BatchUpload` for BS, `ProcessedEssay` for ELS).

---
**3. Event-Driven Communication Backbone**

This is the nervous system of the refactored application.

* **Standardized Event Envelope (Agreed Design)**:
    All events published to the event bus will conform to a standard `EventEnvelope` Pydantic model:
    ```python
    # common/events/envelope.py (New conceptual location)
    from pydantic import BaseModel, Field
    from typing import TypeVar, Generic, Dict, Any, Optional
    from uuid import uuid4, UUID
    from datetime import datetime, timezone

    T_EventData = TypeVar("T_EventData", bound=BaseModel) # Specific Pydantic model for event data

    class EventEnvelope(BaseModel, Generic[T_EventData]):
        event_id: UUID = Field(default_factory=uuid4)
        event_type: str # Fully qualified, versioned name, e.g., "huleedu.essay.spellcheck_concluded.v1"
        event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
        source_service: str # Identifier of the publishing microservice (e.g., "batch-orchestration-service")
        correlation_id: Optional[UUID] = None # For distributed tracing across services
        data_schema_uri: Optional[str] = None # Optional: Link to Pydantic model/JSON schema in a registry
        data: T_EventData # The actual Pydantic model instance for this specific event
    ```
    This provides consistency for event routing, deserialization, basic validation, and observability.

* **Event Payload Structure (`EventEnvelope.data` field)**:
    * The `data` field within the `EventEnvelope` will be a Pydantic model specific to that `event_type`.
    * For events that signify a status change or carry rich processing updates, this Pydantic model will be directly equivalent to (or an evolution of) your `EnhancedProcessingUpdate` or `EventTracker` classes from `common/models/status.py`.
    * **Key Usage Pattern**:
        1.  **Producer Service**: Instantiates the specific Pydantic event data model (e.g., `EssaySpellcheckConcludedDataV1`, which would mirror the structure of `EnhancedProcessingUpdate` but be a concrete Pydantic class). It populates this by passing instances of your metadata models (e.g., `EntityReference`, `SystemProcessingMetadata`, `StorageReferenceMetadata` from `common/models/metadata_models.py`) to the constructor of this Pydantic event data model.
        2.  The service then creates an `EventEnvelope`, putting the Pydantic event data model instance into the `envelope.data` field.
        3.  The `EventEnvelope` instance is serialized (e.g., `envelope.model_dump_json()`) and published.
        4.  **Consumer Service**: Receives the JSON string. Parses it into the `EventEnvelope`. It then uses the `event_type` to determine the specific Pydantic model for the `envelope.data` field and parses `envelope.data` into that typed Pydantic object. This gives type-safe access to all nested metadata.

* **Event Naming Conventions**:
    * Use a clear, hierarchical, past-tense naming convention that includes domain, entity, action, and version. Examples:
        * `batch.orchestration.spellcheck_phase_initiated.v1` (from Batch Orchestrator Service)
        * `essay.lifecycle.spellcheck_requested.v1` (from Essay Lifecycle Service)
        * `spellchecker.essay.correction_concluded.v1` (from SpellChecker Service)
        * `essay.lifecycle.state_updated.v1` (from Essay Lifecycle Service, carrying new `EssayStatus`)
        * `batch.orchestration.pipeline_progress_updated.v1` (from Batch Orchestrator Service, for UI)

* **Thin Events + Callback APIs (Agreed Preference)**:
    * **Principle**: Events primarily signal *that something happened* and provide essential identifiers and key outcome data. They should not carry large data blobs like full essay texts.
    * **Storage References**: Critical for this pattern. Events will carry abstract and stable storage references (URNs or resolvable URIs like `huleedu-storage://{storage_id}`) to data artifacts. Your `StorageReferenceMetadata` model (as a Pydantic model) will encapsulate these references, including `ContentType`.
    * **Callback APIs**: Specialized services (SpellChecker, NLP, AI Feedback) will use these storage references to make asynchronous API calls to a "Content Retrieval Service" (likely part of ELS or a dedicated thin service) to fetch the actual text content needed for processing. This API must be robust, versioned, and highly available.
    * **Rejected**: Universally "fat" events carrying full essay texts or massive metadata objects.

---
**4. State Management for Batch and Essay Processing Pipelines**

This is where your existing enums and metadata models, evolved into Pydantic, become central.

* **A. Batch Orchestrator Service State (`BatchUpload` Entity)**
    * **Primary Status**: Managed by the `BatchUpload.status` field, using values from an *extended* `common.models.enums.BatchStatus` enum. This enum will include distinct top-level states for major phases if they represent significant, externally observable states of the *entire batch* (e.g., `PENDING_INITIAL_PROCESSING`, `PROCESSING_CONTENT_ENRICHMENT` (covering Spellcheck, NLP, AI Feedback as a group), `AWAITING_CJ_ASSESSMENT`, `PROCESSING_CJ_ASSESSMENT`, `COMPLETED`, `FAILED`, `CANCELLED`). The decision for "AI Feedback" to be a top-level batch status depends on whether it's a distinct wait/active state for the *whole batch* from an orchestration perspective, similar to CJ Assessment. Given its complexity as you described (AI Feedback + Editor Revision + dependencies), it likely warrants such top-level representation.
        * *Alternative Considered & Refined*: Initially, we thought of keeping `BatchStatus.PROCESSING` very generic. However, if distinct major pipelines like "AI Feedback Pipeline" and "CJ Assessment Pipeline" are externally significant and the batch explicitly "waits" for them or is "actively in" them, then dedicated top-level `BatchStatus` members are clearer.
    * **Detailed Sub-Phase & Pipeline Tracking (`BatchUpload.processing_metadata` -> `ProcessingPipelineState` Pydantic Model)**:
        * As agreed, this JSONB field will store an instance of a `ProcessingPipelineState` Pydantic model.
        * This model will track the status of *each individual requested processing pipeline* (SpellCheck, NLP, AI Feedback, Editor Revision, Grammar, CJ, etc.) for the batch, using specific sub-phase enums (e.g., `PipelineExecutionStatus`, and potentially more granular ones like `SpellcheckSubPhaseStatus`, `AiFeedbackSubPhaseStatus`).
        * It includes `EssayProcessingCounts` (total, successful, failed, pending) for each pipeline within the batch.
        * It tracks `requested_pipelines` (a list of strings like `["SPELLCHECK", "AI_FEEDBACK", "CJ_ASSESSMENT"]`) defined when the batch is configured for processing.
        * The BS's core orchestration logic iterates based on `requested_pipelines` and the current `status` of each pipeline in `ProcessingPipelineState`, respecting dependencies (e.g., NLP starts after SpellCheck `COMPLETED_SUCCESSFULLY`).
    * **Event Publication for UI & System State (`Batch Orchestrator Service` is the publisher):**
        1.  **Major `BatchStatus` Changes**: When `BatchUpload.status` transitions (e.g., from `PROCESSING_CONTENT_ENRICHMENT` to `AWAITING_CJ_ASSESSMENT`), the BS publishes an `EnhancedProcessingUpdate` based event (e.g., `BATCH_LIFECYCLE_PHASE_CHANGED_V1`).
            * Payload (`EventEnvelope.data` is a Pydantic equivalent of `EnhancedProcessingUpdate`):
                * `event`: e.g., `ProcessingEvent.BATCH_STATUS_UPDATED`.
                * `entity_ref`: For the `BatchUpload`.
                * `status`: The new `BatchStatus` value.
                * `system_metadata`, `batch_metadata` (lean, overall batch stats).
                * `metadata`: `{ "processing_pipeline_state_snapshot": ProcessingPipelineState.to_dict() }`.
        2.  **Granular `ProcessingPipelineState` Updates (for UI/Live Tracking)**: **Crucially**, whenever BS updates the `ProcessingPipelineState` within `BatchUpload.processing_metadata` (e.g., SpellCheck for the batch moves from `IN_PROGRESS` to `COMPLETED_SUCCESSFULLY`, or essay counts change for a pipeline), it **must publish** an event.
            * This uses an `EventTracker`-based Pydantic model (as the primary `BatchStatus` might not have changed).
            * **Event Type**: `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.
            * Payload (`EventEnvelope.data` is a Pydantic equivalent of `EventTracker`):
                * `event`: e.g., `ProcessingEvent.BATCH_PIPELINE_PROGRESS_UPDATED`.
                * `entity_ref`: For the `BatchUpload`.
                * `system_metadata`.
                * `metadata`: `{ "updated_processing_pipeline_state_snapshot": ProcessingPipelineState.to_dict() }`.
            * This directly enables real-time UI updates via the WebSocket service, fulfilling your requirement.
        * **Rejected Approach**: Relying on UI polling `GET /batches/{id}/detailed-progress` as the primary way to get sub-phase updates. Events are primary; API is a fallback or for initial load.

* **B. Essay Lifecycle Service State (`ProcessedEssay` Entity)**
    * **Primary Status**: Managed by `ProcessedEssay.status` field, using an **extended** `common.models.enums.EssayStatus` enum. This enum needs new values to reflect all granular processing steps an essay passes through:
        * `TEXT_EXTRACTED`
        * `AWAITING_SPELLCHECK`, `SPELLCHECKING_IN_PROGRESS` (if SS sends progress), `SPELLCHECKED_SUCCESS`, `SPELLCHECKED_FAILED`
        * `AWAITING_NLP`, `NLP_IN_PROGRESS`, `NLP_COMPLETED_SUCCESS`, `NLP_FAILED`
        * `AWAITING_AI_FEEDBACK`, `AI_FEEDBACK_IN_PROGRESS`, `AI_FEEDBACK_COMPLETED_SUCCESS`, `AI_FEEDBACK_FAILED`
        * `AWAITING_EDITOR_REVISION`, `EDITOR_REVISION_IN_PROGRESS`, `EDITOR_REVISION_COMPLETED_SUCCESS`, `EDITOR_REVISION_FAILED`
        * `AWAITING_GRAMMAR_CHECK`, `GRAMMAR_CHECK_IN_PROGRESS`, `GRAMMAR_CHECK_COMPLETED_SUCCESS`, `GRAMMAR_CHECK_FAILED`
        * `READY_FOR_CJ_ASSESSMENT_INPUT` (all its pre-CJ steps for this batch are done)
        * `CJ_PROCESSING_INVOLVED` (if it's part of a CJ run)
        * `ESSAY_FULLY_PROCESSED_FOR_BATCH` (all *requested pipelines for its batch* are complete for this essay)
        * `ESSAY_PROCESSING_TERMINAL_FAILURE` (a critical, unrecoverable error for this essay).
    * **ELS Event Publication**:
        1.  When ELS dispatches an essay to an SS: Publishes `REQUEST_X_FOR_ESSAY_V1` (e.g., `REQUEST_SPELLCHECK_FOR_ESSAY_V1`). The `EnhancedProcessingUpdate`-based payload has `status = EssayStatus.AWAITING_SPELLCHECK`.
        2.  When ELS consumes a result from an SS (e.g., `ESSAY_SPELLCHECK_CONCLUDED_V1` from SpellChecker, where *that event's* `.status` field contains `EssayStatus.SPELLCHECKED` if SpellChecker successfully updated it):
            * ELS updates its `ProcessedEssay.status` to `EssayStatus.SPELLCHECKED`.
            * ELS stores artifact references from the SS event into `ProcessedEssay.content_metadata`.
            * ELS publishes `ESSAY_LIFECYCLE_STATE_UPDATED_V1`.
                * Payload (`EnhancedProcessingUpdate`-based): `entity_ref` for essay, `status = EssayStatus.SPELLCHECKED.value`, and includes relevant new artifact references (e.g., corrected text storage ID) and possibly a summary of the SS output (like a snippet of the `SpellCheckOutputMetadata`).
                * This event is consumed by BS (to update `ProcessingPipelineState`) and potentially other interested services (like UI via WebSockets for per-essay live updates).

* **C. Specialized Services (SS) Internal State**
    * Each SS (SpellChecker, NLP, AI Feedback, CJ Assessment using its `cj_essay_assessment.db.models_db.BatchStatusEnum` for its *batch-centric internal CJ workflow*) manages its own internal job/task states. These are opaque to other services.
    * When an SS finishes its work on an essay (or a batch in CJ's case), it publishes its concluding event. The `.status` field in the `EnhancedProcessingUpdate`-based payload of this event will use a value from the common `EssayStatus` enum (e.g., `EssayStatus.SPELLCHECKED`) to indicate the *outcome of its processing on that essay in terms of the shared essay lifecycle*. For CJ, its concluding event about a batch will provide a CJ-specific outcome status string (e.g., "CJ_COMPLETED_STABLE") that the Batch Orchestrator Service interprets to set its overall `BatchUpload.status`.

---
**5. Metadata Model Design and Data Propagation**

This builds upon our previous agreement, ensuring clarity and targeted data flow.

* **Common Metadata Models (`common/models/metadata_models.py`)**:
    * Evolved into Pydantic models, these (like `EntityReference`, `SystemProcessingMetadata`, `StorageReferenceMetadata`, `AIFeedbackMetadata`) are the building blocks for the `data` field of the `EventEnvelope`.
    * **New Specialized Output Pydantic Models (in common library)**:
        * `SpellcheckOutputMetadata` (e.g., correction counts, diff log storage ref).
        * `NlpOutputMetadata` (e.g., detailed linguistic features, readability scores storage ref).
        * `GrammarOutputMetadata` (e.g., grammar error categories, counts, suggestions storage ref).
        * `EditorRevisionOutputMetadata` (e.g., revision text storage ref, summary of changes).
        * `CjAssessmentOutputMetadata` (e.g., BT scores, ranking list storage ref, stability metrics).
    * When a Specialized Service completes its task for an essay, its result event's `EnhancedProcessingUpdate`-based payload will include an instance of its specific output metadata model (e.g., AI Feedback Service includes `AIFeedbackMetadata`).

* **Propagation of Contextual Data (e.g., `course_code`, `teacher_name`, `essay_instructions`, `student_name`):**
    1.  **Batch Orchestrator Service (BS)** owns batch-level context (`course_code`, `teacher_name` derived from `BatchUpload.user_id`, `class_designation`, `essay_instructions` from its `BatchUpload` entity).
    2.  When BS publishes a batch-level command to ELS (e.g., `INITIATE_AI_FEEDBACK_FOR_BATCH_V1`), the `BatchProcessingMetadata` within that event carries this batch context. The event also lists the essays to be processed.
    3.  **Essay Lifecycle Service (ELS)** consumes this. For *each* essay it needs to dispatch to a Specialized Service:
        * It fetches its own essay-specific data (like `student_name` for that essay from `ProcessedEssay.student_name`).
        * It **assembles a tailored `input_context` dictionary** for the target Specialized Service. This `input_context` includes:
            * Relevant fields copied from the `BatchProcessingMetadata` it received (e.g., `course_code`, `essay_instructions`, `teacher_name`, `class_designation`).
            * Essay-specific data it owns (e.g., `student_name`).
            * References to any prerequisite artifacts (e.g., `spellchecked_text_storage_id`, `nlp_metrics_storage_id`).
        * ELS then publishes the essay-specific command (e.g., `REQUEST_AI_FEEDBACK_FOR_ESSAY_V1`). The `EnhancedProcessingUpdate`-based payload includes this `input_context` dictionary within its generic `metadata` field.
    4.  **Specialized Service (e.g., AI Feedback Service):**
        * Consumes the event from ELS and extracts the `input_context`.
        * Uses this context to perform its work.
        * When it produces its output metadata (e.g., an instance of `AIFeedbackMetadata`), it **copies the relevant fields from the `input_context` it received** into this `AIFeedbackMetadata` instance. This makes the `AIFeedbackMetadata` artifact (and the event carrying it) self-descriptive regarding the conditions under which it was generated.
    * **Rejected**: Having Specialized Services always call back to BS or ELS for basic operational context if that context is essential for their task and relatively stable for that task instance.

* **Simplified `BatchProcessingMetadata`**:
    * The primary `BatchProcessingMetadata` instance associated with a `BatchUpload` (and included in batch-level status events from BS) can focus on overall batch identity, configuration (`requested_pipelines`), aggregate statistics (`total_essays`, overall progress summaries if not fully covered by `ProcessingPipelineState`), and final outcomes.
    * It does *not* need to be the carrier of all possible contextual details for every downstream service simultaneously. That context is passed more selectively by BS/ELS in the initiation events for specific pipelines.

* **`TaskProcessingMetadata`**:
    * Remains useful for the *internal* task tracking of any service performing an asynchronous operation. When that service publishes an event related to its task's outcome, including its `TaskProcessingMetadata` provides observability into *its* internal workings for that specific event.

---
**6. API Endpoint Design for Microservices**

(This section remains largely consistent with previous good advice, emphasizing async initiation for batch processes).

* **Batch Orchestrator Service APIs**:
    * `POST /v1/batches`: Create a new batch (upload essays). Returns `202 Accepted` with `batch_id` and status monitoring URL. Triggers internal processing and the `BatchStatus.UPLOADED` state.
    * `POST /v1/batches/{batch_id}/configure-pipelines`: (New) Allows user to specify `requested_pipelines` and any pipeline-specific configurations. Transitions batch to `BatchStatus.PENDING`.
    * `POST /v1/batches/{batch_id}/start-processing`: (New) User explicitly starts the configured pipelines. Batch Orchestrator Service initiates the first phase.
    * `GET /v1/batches/{batch_id}`: Returns overall `BatchUpload` info, including current `BatchStatus` and the full `ProcessingPipelineState` from `processing_metadata`.
    * `GET /v1/batches/{batch_id}/essays`: Paginated list of `essay_id`s and their current `EssayStatus` (ELS might provide this data, or BS aggregates it).
* **Essay Lifecycle Service APIs**:
    * `GET /v1/essays/{essay_id}`: Detailed info for a single essay, including its current `EssayStatus`, all associated artifact `storage_id`s, and potentially summaries of its processing metadata (like `AIFeedbackMetadata` snapshot).
    * `GET /v1/essays/{essay_id}/content/{content_type}`: Retrieves specific content (e.g., original, spellchecked, AI feedback text) via the Content Retrieval Service.
* **Specialized Service APIs (mostly internal or for specific artifact retrieval):**
    * E.g., AI Feedback Service: `GET /v1/ai-feedback/artifacts/{essay_id}/{artifact_type_or_id}`.
* **General API Principles**: Resource-oriented, Pydantic schemas for request/response, OpenAPI docs, versioning, standard error handling (using `ErrorInfoModel`), idempotency for state-changing requests.

---
**7. Consumer-Driven Contracts (CDC)**

(This also remains consistent, emphasizing evolution from your `EventContract.py` towards consumer-published Pydantic pacts and automated contract testing).

* Your common library of Pydantic models (evolved from `metadata_models.py`, `status.py`, `batch.py`, `user.py`, new `pipeline_state_models.py`, new specialized output metadata models) **is the core of all contracts**.
* An `EventContract` entry for a `ProcessingEvent` like `BATCH_PIPELINE_PROGRESS_UPDATED` would now clearly state that its `EventEnvelope.data` (which is `EventTracker`-based) will contain a `metadata` field, which in turn has a `processing_pipeline_state_snapshot` key whose value conforms to the `ProcessingPipelineState` Pydantic model.

---
**8. Impact on Other System Components & Refactoring Effort**

* **UI**: Heavily reliant on WebSocket service pushing `BATCH_PIPELINE_PROGRESS_UPDATED_V1` events (containing `ProcessingPipelineState`) and `ESSAY_LIFECYCLE_STATE_UPDATED_V1` events for rich, real-time views. Initial data loads via Batch/Essay service APIs.
* **User/Auth Service**: Unchanged in its core role; provides user context for BS.
* **Notification/WebSocket Service**: Central consumer of progress events from BS and ELS to relay to UI.
* **File Upload/Ingestion**: This initial stage is critical. It must correctly create `BatchUpload` and `ProcessedEssay` records (likely via commands to BS/ELS) and store initial essay texts, generating the first `storage_id`s.
* **Database Design**:
    * Batch Orchestrator Service needs robust storage for `BatchUpload` including the JSONB `processing_metadata` (for `ProcessingPipelineState`).
    * Batch Orchestrator Service needs robust storage for `BatchUpload` including the JSONB `processing_metadata` (for `ProcessingPipelineState`).
    * Essay Lifecycle Service needs robust storage for `ProcessedEssay` including its `EssayStatus` and `content_metadata` (for storing results and artifact links from various SS).
    * Each SS owns its specific data if it needs to persist more than what it outputs in events.
* **Refactoring Effort**:
    * Definitively splitting `server_web_app` logic into a Batch Orchestrator Service and an Essay Lifecycle Service (or clearly demarcating these responsibilities within one service).
    * Extending `common.models.enums.EssayStatus` and possibly `BatchStatus`.
    * Creating the Pydantic `ProcessingPipelineState` model and associated sub-phase enums.
    * Implementing the orchestration logic within BS to manage `ProcessingPipelineState` based on dependencies and incoming essay lifecycle events.
    * Ensuring BS and ELS publish the fine-grained progress events needed for the UI.
    * Adapting all Specialized Services to consume targeted context from ELS and publish results with the correct common `EssayStatus` and their specific output metadata.

---
**9. Conclusion**

This refined design provides a highly flexible, scalable, and observable event-driven system. By making the Batch Orchestrator Service an orchestrator of *processing pipelines* (whose states are tracked in detail within `ProcessingPipelineState`) rather than a manager of a rigid, linear batch status, you can accommodate complex and varying processing needs. The Essay Lifecycle Service manages the granular states of individual essays as they flow through these pipelines. Crucially, real-time UI updates are driven by events carrying detailed progress snapshots, fulfilling your core requirement for an interactive, asynchronous system. All inter-service communication is based on explicit, Pydantic-defined contracts derived from your well-structured common models.


## Architectural Blueprint: Refactored HuleEdu Services in Practice

This example illustrates the core event flows, state management, and data structures for key microservices in the refactored HuleEdu system. It builds directly upon your existing models and our agreed-upon design decisions.

**Scenario Focus:** A batch of essays undergoes a pipeline involving initial setup, spell-checking, and AI feedback, showcasing inter-service event communication, state transitions, and progress tracking for UI updates.

---
**1. Core Pydantic Models, Enums & Key Data Structures (Recap & Extensions)**

We assume your existing dataclasses from `common/models/` will be evolved into Pydantic models. For this example, we'll refer to them as such.

* **Key Pydantic Models (based on your `common/models/`)**:
    * `EntityReference`, `SystemProcessingMetadata`, `BatchProcessingMetadata`, `AIFeedbackMetadata`, `StorageReferenceMetadata`, `TaskProcessingMetadata`, `ErrorInfoModel` (all from `common/models/metadata_models.py` and `common/models/error_info_model.py`).
    * The Pydantic equivalents of `EventBase`, `EnhancedProcessingUpdate`, and `EventTracker` (from `common/models/status.py`) will form the basis for specific event data payloads.
    * `BatchUploadData` and `ProcessedEssayData` (Pydantic versions of models in `common/models/batch.py`).

* **Extended Enums (from `common/models/enums.py`)**:

    ```python
    # common/models/enums.py (Conceptual Extensions)
    from enum import Enum
    # Assuming ProcessingStage is defined in common.terminology or similar
    # from common.terminology import ProcessingStage 

    class ProcessingStage(str, Enum): # Assuming this exists based on your files
        PENDING = "pending"
        INITIALIZED = "initialized"
        PROCESSING = "processing"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"

    class ProcessingEvent(str, Enum):
        # Batch Orchestration Events
        BATCH_PIPELINE_REQUESTED = "batch.pipeline.requested" # User/system requests pipelines for a batch
        BATCH_PHASE_INITIATED = "batch.phase.initiated"     # BS initiates a major phase (e.g. spellcheck for all essays)
        BATCH_PIPELINE_PROGRESS_UPDATED = "batch.pipeline.progress.updated" # Granular progress update from BS
        BATCH_PHASE_CONCLUDED = "batch.phase.concluded"       # BS concludes a major phase
        BATCH_LIFECYCLE_COMPLETED = "batch.lifecycle.completed" # All requested pipelines for batch done
        BATCH_LIFECYCLE_FAILED = "batch.lifecycle.failed"
        BATCH_LIFECYCLE_PARTIALLY_COMPLETED = "batch.lifecycle.partially_completed"

        # Essay Lifecycle Events (from ELS)
        ESSAY_PHASE_INITIATION_REQUESTED = "essay.phase.initiation.requested" # ELS to Specialized Service
        ESSAY_LIFECYCLE_STATE_UPDATED = "essay.lifecycle.state.updated" # ELS publishes this after SS result

        # Specialized Service Result Events (from SS to ELS)
        ESSAY_SPELLCHECK_RESULT_RECEIVED = "essay.spellcheck.result.received"
        ESSAY_NLP_RESULT_RECEIVED = "essay.nlp.result.received"
        ESSAY_AIFEEDBACK_RESULT_RECEIVED = "essay.aifeedback.result.received"
        ESSAY_EDITOR_REVISION_RESULT_RECEIVED = "essay.editor_revision.result.received"
        ESSAY_GRAMMAR_RESULT_RECEIVED = "essay.grammar.result.received"
        
        # General
        PROCESSING_STARTED = "processing.started" # Generic start
        PROCESSING_COMPLETED = "processing.completed" # Generic completion
        PROCESSING_FAILED = "processing.failed"
        # ... other existing ProcessingEvents ...
        FEEDBACK_STARTED = "feedback.started" # from status.py
        FEEDBACK_COMPLETED = "feedback.completed" # from status.py
        FEEDBACK_FAILED = "feedback.failed" # from status.py
        BATCH_PROCESSING_STARTED = "batch.processing.started" # from status.py
        BATCH_PROCESSING_COMPLETED = "batch.processing.completed" # from status.py

    class EssayStatus(str, Enum): # Extended
        UPLOADED = "uploaded"
        TEXT_EXTRACTED = "text_extracted"
        
        AWAITING_SPELLCHECK = "awaiting_spellcheck"
        SPELLCHECKING_IN_PROGRESS = "spellchecking_in_progress" # If SS provides such updates
        SPELLCHECKED_SUCCESS = "spellchecked_success"
        SPELLCHECK_FAILED = "spellcheck_failed"
        
        AWAITING_NLP = "awaiting_nlp"
        NLP_PROCESSING_IN_PROGRESS = "nlp_processing_in_progress"
        NLP_COMPLETED_SUCCESS = "nlp_completed_success"
        NLP_FAILED = "nlp_failed"

        AWAITING_AI_FEEDBACK = "awaiting_ai_feedback"
        AI_FEEDBACK_PROCESSING_IN_PROGRESS = "ai_feedback_processing_in_progress"
        AI_FEEDBACK_COMPLETED_SUCCESS = "ai_feedback_completed_success"
        AI_FEEDBACK_FAILED = "ai_feedback_failed"

        AWAITING_EDITOR_REVISION = "awaiting_editor_revision"
        EDITOR_REVISION_PROCESSING_IN_PROGRESS = "editor_revision_processing_in_progress"
        EDITOR_REVISION_COMPLETED_SUCCESS = "editor_revision_completed_success"
        EDITOR_REVISION_FAILED = "editor_revision_failed"

        AWAITING_GRAMMAR_CHECK = "awaiting_grammar_check"
        GRAMMAR_CHECK_PROCESSING_IN_PROGRESS = "grammar_check_processing_in_progress"
        GRAMMAR_CHECK_COMPLETED_SUCCESS = "grammar_check_completed_success"
        GRAMMAR_CHECK_FAILED = "grammar_check_failed"

        AWAITING_CJ_INCLUSION = "awaiting_cj_inclusion" # Ready to be considered for a CJ batch run
        CJ_PROCESSING_ACTIVE = "cj_processing_active" # Actively part of a CJ run
        CJ_RANKING_COMPLETED = "cj_ranking_completed"
        CJ_PROCESSING_FAILED = "cj_processing_failed"

        # Terminal states for an essay's journey through ALL requested pipelines
        ESSAY_ALL_PROCESSING_COMPLETED = "essay_all_processing_completed"
        ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES = "essay_partially_processed_with_failures"
        ESSAY_CRITICAL_FAILURE = "essay_critical_failure" # A failure preventing further processing
        
        # Original states from your file
        PENDING = "pending" # Generic pending for a step
        PROCESSING = "processing" # Generic processing for a step
        COMPLETED = "completed" # Generic completed for a step (use more specific ones above)
        FAILED = "failed" # Generic failed for a step (use more specific ones above)
        CANCELLED = "cancelled"

    class BatchStatus(str, Enum): # Potentially extended
        UPLOADED = "uploaded"
        PARTIALLY_UPLOADED = "partially_uploaded"
        PENDING_CONFIGURATION = "pending_configuration" # Batch created, awaiting pipeline selection
        PENDING_PROCESSING_INITIATION = "pending_processing_initiation" # Configured, ready for user to start
        
        PROCESSING_CONTENT_ENRICHMENT = "processing_content_enrichment" # Overall phase for Spellcheck, NLP, AI Feedback, Grammar, EditorRevision
        AWAITING_CJ_ASSESSMENT = "awaiting_cj_assessment"
        PROCESSING_CJ_ASSESSMENT = "processing_cj_assessment"
        
        # Original states - PROCESSING becomes a general state if specific pipeline states aren't used
        PENDING = "pending" # Generic: Awaiting next major phase or user action
        PROCESSING = "processing" # Generic: Actively being worked on (details in metadata)
        COMPLETED = "completed" # All requested pipelines for the batch are successfully done
        PARTIALLY_COMPLETED = "partially_completed" # All requested pipelines concluded, but some essays had issues or a pipeline was interrupted but yielded partial results
        FAILED = "failed" # Batch-level critical failure or too many essay failures
        CANCELLED = "cancelled"

    # Other enums like ContentType, ErrorCode remain as per your common/models/enums.py
    class ContentType(str, Enum):
        ORIGINAL_ESSAY = "original_essay"
        CORRECTED_TEXT = "corrected_text"
        PROCESSING_LOG = "processing_log" # e.g. for spellcheck diffs
        NLP_METRICS_JSON = "nlp_metrics_json"
        STUDENT_FACING_AI_FEEDBACK_TEXT = "student_facing_ai_feedback_text"
        AI_EDITOR_REVISION_TEXT = "ai_editor_revision_text"
        AI_DETAILED_ANALYSIS_JSON = "ai_detailed_analysis_json" # Internal AI metrics
        GRAMMAR_ANALYSIS_JSON = "grammar_analysis_json"
        CJ_RESULTS_JSON = "cj_results_json"

    class ErrorCode(str, Enum):
        # General
        UNKNOWN_ERROR = "UNKNOWN_ERROR"
        VALIDATION_ERROR = "VALIDATION_ERROR"
        RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
        # Specialized services
        SPELLCHECK_SERVICE_ERROR = "SPELLCHECK_SERVICE_ERROR"
        NLP_SERVICE_ERROR = "NLP_SERVICE_ERROR"
        AI_FEEDBACK_SERVICE_ERROR = "AI_FEEDBACK_SERVICE_ERROR"
        CJ_ASSESSMENT_SERVICE_ERROR = "CJ_ASSESSMENT_SERVICE_ERROR"
        # ... more specific error codes ...
    ```

* **`ProcessingPipelineState` Pydantic Model (conceptual, in `common/models/pipeline_models.py`)**:
    (As detailed in the previous response, with `PipelineExecutionStatus` enum and `PipelineStateDetail` for each pipeline like `spellcheck`, `nlp_metrics`, `ai_feedback`, `ai_editor_revision`, `grammar_check`, `cj_assessment`).

* **Standard `EventEnvelope` Pydantic Model (as detailed previously).**

---
**2. Service Definitions & Interactions (Conceptual Python-like Code with Type Hints)**

We'll focus on Batch Orchestrator Service (BS), Essay Lifecycle Service (ELS), SpellChecker Service (SS_Spell), and AI Feedback Service (SS_AI).

```python
# --- common/events/publisher.py (Conceptual) ---
from typing import Any, Callable, Dict, Type
from pydantic import BaseModel
# from common.events.envelope import EventEnvelope # Defined above
# from common.models.status import EnhancedProcessingUpdate, EventTracker # Pydantic versions

# Placeholder for event publishing mechanism (e.g., Redis Pub/Sub, Kafka)
EventBusClient = Any 

async def publish_event(
    bus_client: EventBusClient, 
    topic: str, 
    event_data_model: BaseModel, # Specific Pydantic model for EventEnvelope.data
    event_type_str: str, # e.g., "huleedu.batch.phase_initiated.v1"
    source_service_name: str,
    correlation_id: Optional[str] = None,
    data_schema_uri: Optional[str] = None
) -> None:
    envelope = EventEnvelope[type(event_data_model)]( # Ensure type hint for data
        event_type=event_type_str,
        source_service=source_service_name,
        correlation_id=correlation_id,
        data_schema_uri=data_schema_uri,
        data=event_data_model
    )
    message_payload_json: str = envelope.model_dump_json()
    # In a real system, this would send to Kafka, Redis Streams, etc.
    print(f"PUBLISHING to topic '{topic}': {message_payload_json}") 
    # await bus_client.publish(topic, message_payload_json)
    pass

# --- common/events/data_models.py (Specific Pydantic models for EventEnvelope.data) ---
# These would be Pydantic versions mirroring EnhancedProcessingUpdate / EventTracker structure
# but typed for specific events.

from common.models.metadata_models import ( # Assuming Pydantic versions
    EntityReference, SystemProcessingMetadata, BatchProcessingMetadata, 
    AIFeedbackMetadata, StorageReferenceMetadata, TaskProcessingMetadata
)
# from common.models.enums import ProcessingEvent, BatchStatus, EssayStatus # Extended enums

# Base for our event data models, mimicking parts of EnhancedProcessingUpdate/EventTracker
class BaseEventData(BaseModel):
    event: str # From ProcessingEvent enum, specific to this event's business meaning
    entity_ref: EntityReference
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    system_metadata: SystemProcessingMetadata # Populated for this specific event instance

class EnhancedProcessingUpdateEventData(BaseEventData): # For events signifying status change
    status: str # Value from BatchStatus or EssayStatus enum

class EventTrackerEventData(BaseEventData): # For informational events not changing primary status
    pass

# --- Batch Orchestrator Service specific event data models ---
class InitiatePipelineForBatchDataV1(EnhancedProcessingUpdateEventData):
    batch_metadata: BatchProcessingMetadata # Snapshot of batch context
    # Custom metadata for this specific event type
    # Replaces the generic 'metadata' field from EnhancedProcessingUpdate for type safety
    pipeline_initiation_details: Dict[str, Any] # e.g., {"essays_to_process": [...], "target_pipeline": "SPELLCHECK"}

class BatchPipelineProgressUpdatedDataV1(EventTrackerEventData):
    # No primary status change for the BatchUpload entity itself
    # The progress is in the pipeline_state_snapshot
    # from common.models.pipeline_models import ProcessingPipelineState # Defined in previous response
    # pipeline_state_snapshot: ProcessingPipelineState # The updated state
    pipeline_state_snapshot_dict: Dict[str, Any] # Serialized ProcessingPipelineState

# --- Essay Lifecycle Service specific event data models ---
class RequestProcessingForEssayDataV1(EnhancedProcessingUpdateEventData):
    # 'status' here would be the new EssayStatus like AWAITING_SPELLCHECK
    # Custom metadata for this specific event type
    essay_processing_request_details: Dict[str, Any] 
    # e.g. {"text_storage_id": "...", "correlating_batch_ref_dict": {...}, "input_context_for_ss": {...}}

class EssayLifecycleStateUpdatedDataV1(EnhancedProcessingUpdateEventData):
    # 'status' here is the new confirmed EssayStatus (e.g., SPELLCHECKED_SUCCESS)
    # It might also carry resulting metadata from the specialized service
    # For example, if it just received AIFeedbackMetadata, it might pass a summary or ref.
    # Custom metadata for this specific event type
    essay_update_details: Dict[str, Any] # e.g. {"updated_artifact_refs": [...]}


# --- Specialized Service (SS) result event data models (SS -> ELS) ---
class EssaySpellcheckResultDataV1(EnhancedProcessingUpdateEventData):
    # 'status' is EssayStatus.SPELLCHECKED_SUCCESS or EssayStatus.SPELLCHECK_FAILED
    # from common.models.metadata_models import StorageReferenceMetadata # Pydantic version
    # Custom metadata
    # spellcheck_output_metadata: Optional[SpellcheckOutputMetadata] # If defined
    storage_metadata: Optional[StorageReferenceMetadata] # Refs to corrected text, logs
    result_summary: Dict[str, Any] # e.g. {"corrections_made": 10}

class EssayAIFeedbackResultDataV1(EnhancedProcessingUpdateEventData):
    # 'status' is EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS or EssayStatus.AI_FEEDBACK_FAILED
    ai_feedback_metadata: AIFeedbackMetadata # The full output from AI service
    storage_metadata: StorageReferenceMetadata # Refs to feedback text, detailed analysis JSON
    # result_summary: Dict[str, Any] # Could be part of ai_feedback_metadata


# --- BatchOrchestrationService (BS) ---
# Owns BatchUpload entities and their ProcessingPipelineState (in processing_metadata)
# Uses common.models.enums.BatchStatus

class BatchOrchestrationService:
    def __init__(self, event_bus_client: EventBusClient, db_repo: Any # BatchUploadRepository
                ):
        self.bus = event_bus_client
        self.repo = db_repo # Placeholder for DB interaction
        self.service_name = "batch-orchestration-service"

    async def handle_configure_batch_pipelines(
        self, 
        batch_id: UUID, 
        requested_pipelines: List[str], # e.g., ["SPELLCHECK", "AI_FEEDBACK"]
        user_id: str, # For audit/context
        correlation_id: Optional[UUID] = None
    ) -> bool:
        batch_upload: Optional[Dict] = await self.repo.get_batch_upload_by_id(batch_id)
        if not batch_upload:
            # Handle error: batch not found
            return False

        # Initialize ProcessingPipelineState
        # from common.models.pipeline_models import ProcessingPipelineState, PipelineStateDetail, PipelineExecutionStatus
        pipeline_state = ProcessingPipelineState(requested_pipelines=requested_pipelines)
        for pipeline_name in requested_pipelines:
            if hasattr(pipeline_state, pipeline_name.lower()):
                getattr(pipeline_state, pipeline_name.lower()).status = PipelineExecutionStatus.REQUESTED_BY_USER
        
        # Update batch_upload.processing_metadata with pipeline_state.model_dump()
        # Update batch_upload.status to BatchStatus.PENDING_PROCESSING_INITIATION.value
        updated_batch: bool = await self.repo.update_batch_processing_details(
            batch_id, 
            BatchStatus.PENDING_PROCESSING_INITIATION.value, 
            pipeline_state.model_dump(mode='json') # Store as JSON
        )
        if not updated_batch: return False

        # Publish event confirming batch is configured and pending initiation
        # from common.models.metadata_models import EntityReference, SystemProcessingMetadata, BatchProcessingMetadata
        # from common.models.enums import ProcessingEvent
        
        batch_entity_ref = EntityReference(entity_id=str(batch_id), entity_type="batch")
        sys_meta = SystemProcessingMetadata(
            entity=batch_entity_ref, 
            event=ProcessingEvent.BATCH_STATUS_UPDATED.name, # Or a new event type
            timestamp=datetime.now(timezone.utc)
        )
        # batch_meta_obj = await self.repo.get_batch_processing_metadata_snapshot(batch_id) # Get current BatchProcessingMetadata

        # Example, assuming batch_meta_obj is constructed based on batch_upload
        batch_meta_obj = BatchProcessingMetadata(
            user_id=batch_upload.get("user_id"),
            file_count=batch_upload.get("initial_file_count",0), 
            total_essays=batch_upload.get("initial_total_essays",0),
            # ... other relevant fields for a general batch update
        )


        event_data = EnhancedProcessingUpdateEventData(
            event=ProcessingEvent.BATCH_STATUS_UPDATED.name, # Or new BATCH_PIPELINES_CONFIGURED
            entity_ref=batch_entity_ref,
            status=BatchStatus.PENDING_PROCESSING_INITIATION.value,
            system_metadata=sys_meta
            # If EnhancedProcessingUpdateEventData is extended for specific metadata layers:
            # batch_metadata=batch_meta_obj 
        )
        # Add pipeline_state_snapshot to the custom metadata part if not directly on event_data
        # For this example, let's assume it's a common pattern to include it in a generic progress event
        
        await publish_event(
            self.bus, 
            topic=f"batch.lifecycle.{batch_id}.status_updated.v1",
            event_data_model=event_data,
            event_type_str="huleedu.batch.status_updated.v1", # Full event type name
            source_service_name=self.service_name,
            correlation_id=str(correlation_id) if correlation_id else None
        )
        return True

    async def handle_start_batch_processing(
        self, 
        batch_id: UUID, 
        correlation_id: Optional[UUID] = None
    ) -> bool:
        # This is called when user explicitly starts the configured pipelines
        batch_upload: Optional[Dict] = await self.repo.get_batch_upload_by_id(batch_id)
        if not batch_upload or batch_upload.get("status") != BatchStatus.PENDING_PROCESSING_INITIATION.value:
            # Handle error: batch not ready or not found
            return False

        # Update batch_upload.status to BatchStatus.PROCESSING.value
        # Then, call _check_dependencies_and_initiate_next_pipeline
        await self.repo.update_batch_status(batch_id, BatchStatus.PROCESSING.value)
        
        # from common.models.metadata_models import EntityReference, SystemProcessingMetadata
        # from common.models.enums import ProcessingEvent
        batch_entity_ref = EntityReference(entity_id=str(batch_id), entity_type="batch")
        sys_meta = SystemProcessingMetadata(
            entity=batch_entity_ref, event=ProcessingEvent.BATCH_PROCESSING_STARTED.name
        )
        event_data = EnhancedProcessingUpdateEventData(
            event=ProcessingEvent.BATCH_PROCESSING_STARTED.name,
            entity_ref=batch_entity_ref,
            status=BatchStatus.PROCESSING.value,
            system_metadata=sys_meta
        )
        await publish_event(
            self.bus, f"batch.lifecycle.{batch_id}.processing_started.v1", event_data,
            "huleedu.batch.processing_started.v1", self.service_name, str(correlation_id) if correlation_id else None
        )

        await self._check_dependencies_and_initiate_next_pipeline(batch_id, correlation_id)
        return True

    async def _update_and_publish_pipeline_progress(
        self, 
        batch_id: UUID, 
        pipeline_state: "ProcessingPipelineState", # Forward reference
        correlation_id: Optional[UUID] = None,
        changed_pipeline: Optional[str] = None, # e.g., "SPELLCHECK"
        changed_essay_id: Optional[UUID] = None
    ) -> None:
        # Save the updated pipeline_state to BatchUpload.processing_metadata in DB
        await self.repo.update_batch_pipeline_state(batch_id, pipeline_state.model_dump(mode='json'))

        # Publish BATCH_PIPELINE_PROGRESS_UPDATED_V1 (using EventTracker based model)
        # from common.models.metadata_models import EntityReference, SystemProcessingMetadata
        # from common.models.enums import ProcessingEvent
        batch_entity_ref = EntityReference(entity_id=str(batch_id), entity_type="batch")
        sys_meta = SystemProcessingMetadata(
            entity=batch_entity_ref, event=ProcessingEvent.BATCH_PIPELINE_PROGRESS_UPDATED.name
        )
        
        # Construct the specific data model for this event
        progress_event_data = BatchPipelineProgressUpdatedDataV1(
            event=ProcessingEvent.BATCH_PIPELINE_PROGRESS_UPDATED.name,
            entity_ref=batch_entity_ref,
            system_metadata=sys_meta,
            pipeline_state_snapshot_dict=pipeline_state.model_dump(mode='json') # Send the whole state
        )
        
        # Add custom fields if needed for more specific UI updates
        # if hasattr(progress_event_data, 'custom_details'):
        #     progress_event_data.custom_details = {
        #         "changed_pipeline_for_ui": changed_pipeline,
        #         "changed_essay_id_for_ui": str(changed_essay_id) if changed_essay_id else None
        #     }

        await publish_event(
            self.bus,
            topic=f"batch.progress.{batch_id}.updated.v1",
            event_data_model=progress_event_data,
            event_type_str="huleedu.batch.pipeline_progress_updated.v1",
            source_service_name=self.service_name,
            correlation_id=str(correlation_id) if correlation_id else None
        )

    async def _check_dependencies_and_initiate_next_pipeline(
        self, 
        batch_id: UUID, 
        correlation_id: Optional[UUID] = None
    ) -> None:
        # Complex logic:
        # 1. Fetch current BatchUpload and its ProcessingPipelineState.
        # 2. Iterate through `pipeline_state.requested_pipelines`.
        # 3. For each pipeline that is REQUESTED_BY_USER or PENDING_DEPENDENCIES:
        #    a. Check if its dependencies are met (e.g., for NLP, is spellcheck.status COMPLETED_SUCCESSFULLY?).
        #    b. If met:
        #       i.   Update pipeline_state for this pipeline (e.g., to DISPATCH_INITIATED, set counts).
        #       ii.  Call _update_and_publish_pipeline_progress.
        #       iii. Construct and publish the batch-level command event to ELS,
        #            e.g., INITIATE_SPELLCHECK_FOR_BATCH_V1.
        #            This event's data model (e.g., InitiatePipelineForBatchDataV1) would include:
        #            - batch_entity_ref
        #            - A snapshot of relevant BatchProcessingMetadata (course_code, teacher_name, etc. for AI Feedback)
        #            - List of {"essay_id": ..., "current_text_storage_id": ...}
        #            - The target pipeline name (e.g., "SPELLCHECK")
        # Example for initiating AI Feedback:
        # if pipeline_state.ai_feedback.status == PipelineExecutionStatus.PENDING_DEPENDENCIES and \
        #    pipeline_state.spellcheck.status == PipelineExecutionStatus.COMPLETED_SUCCESSFULLY and \
        #    pipeline_state.nlp_metrics.status == PipelineExecutionStatus.COMPLETED_SUCCESSFULLY: # Or based on config
            
            # Update pipeline_state.ai_feedback status to DISPATCH_INITIATED, set counts
            # ...
            # await self._update_and_publish_pipeline_progress(...)

            # Fetch necessary context from BatchUpload / BatchProcessingMetadata
            # batch_context_for_ai = BatchProcessingMetadata(...) # Populated
            # essays_to_process_for_ai = await self.repo.get_essays_for_pipeline_step(batch_id, "AI_FEEDBACK")

            # Construct InitiatePipelineForBatchDataV1 for AI Feedback
            # from common.models.metadata_models import EntityReference, SystemProcessingMetadata, BatchProcessingMetadata
            # from common.models.enums import ProcessingEvent
            # batch_entity_ref = EntityReference(entity_id=str(batch_id), entity_type="batch")
            # sys_meta = SystemProcessingMetadata(entity=batch_entity_ref, event=ProcessingEvent.BATCH_PHASE_INITIATED.name)
            # batch_meta_snapshot = await self.repo.get_batch_processing_metadata_for_event(batch_id)

            # initiation_details = {
            #    "essays_to_process": essays_to_process_for_ai, # list of {"essay_id": id, "current_text_storage_id": ref}
            #    "target_pipeline_name": "AI_FEEDBACK",
            #    "pipeline_specific_config": {"prompt_version": "v3"}, # Example
                 # Include batch-level context needed by AI service, as discussed
            #    "batch_context_for_ai": batch_meta_snapshot.model_dump( # Or a subset
            #         include={'teacher_name', 'course_code', 'essay_instructions', 'class_designation'}
            #    ) if batch_meta_snapshot else {}
            # }
            # event_data = InitiatePipelineForBatchDataV1(
            #     event=ProcessingEvent.BATCH_PHASE_INITIATED.name,
            #     entity_ref=batch_entity_ref,
            #     status=BatchStatus.PROCESSING.value, # Batch is still PROCESSING
            #     system_metadata=sys_meta,
            #     batch_metadata=batch_meta_snapshot, # Overall batch metadata
            #     pipeline_initiation_details=initiation_details
            # )
            # await publish_event(self.bus, f"els.command.initiate_pipeline_for_batch.{batch_id}.v1", 
            #                     event_data, "huleedu.els.command.initiate_pipeline.v1", 
            #                     self.service_name, str(correlation_id) if correlation_id else None)
        pass

    async def handle_essay_pipeline_step_concluded(
        self, 
        event_envelope_dict: Dict[str, Any], # Assuming this is already the deserialized EventEnvelope dict
        correlation_id: Optional[UUID] = None
    ) -> None:
        # This consumes events like ELS's EssayLifecycleStateUpdatedDataV1
        # Reconstruct the event data from event_envelope_dict["data"]
        # event_data = EssayLifecycleStateUpdatedDataV1.model_validate(event_envelope_dict["data"])
        
        # batch_id = event_data.entity_ref.parent_id # Assuming essay entity_ref has parent_id as batch_id
        # essay_id = event_data.entity_ref.entity_id
        # essay_new_status: EssayStatus = EssayStatus(event_data.status)
        # pipeline_step_name = event_data.essay_update_details.get("pipeline_step_completed") # e.g. "SPELLCHECK"
        
        # Fetch current BatchUpload and its ProcessingPipelineState
        # batch_upload = await self.repo.get_batch_upload_by_id(batch_id)
        # pipeline_state = ProcessingPipelineState.model_validate(batch_upload.processing_metadata.get("processing_pipeline_state"))

        # Update pipeline_state.XXX_pipeline.essay_counts based on essay_new_status
        # If essay_new_status indicates success for pipeline_step_name:
        #   pipeline_state.get_pipeline(pipeline_step_name).essay_counts.successful += 1
        # Else if failure:
        #   pipeline_state.get_pipeline(pipeline_step_name).essay_counts.failed += 1
        # pipeline_state.get_pipeline(pipeline_step_name).essay_counts.pending_dispatch_or_processing -=1

        # Check if all essays for this pipeline_step_name are done for this batch
        # if pipeline_state.get_pipeline(pipeline_step_name).essay_counts.pending_dispatch_or_processing == 0:
        #   Update pipeline_state.get_pipeline(pipeline_step_name).status (e.g., to COMPLETED_SUCCESSFULLY)
        #   pipeline_state.get_pipeline(pipeline_name).completed_at = datetime.now(timezone.utc)
        
        # await self._update_and_publish_pipeline_progress(batch_id, pipeline_state, correlation_id, pipeline_step_name, essay_id)
        
        # After updating progress, check if this completion unblocks other pipelines
        # await self._check_dependencies_and_initiate_next_pipeline(batch_id, correlation_id)

        # Finally, check if ALL requested pipelines for the batch are complete
        # all_requested_done = True
        # for req_pipe_name in pipeline_state.requested_pipelines:
        #    pipe_state_detail = getattr(pipeline_state, req_pipe_name.lower())
        #    if pipe_state_detail.status not in [PipelineExecutionStatus.COMPLETED_SUCCESSFULLY, 
        #                                        PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS,
        #                                        PipelineExecutionStatus.COMPLETED_WITH_ERRORS, # Or FAILED_PIPELINE
        #                                        PipelineExecutionStatus.SKIPPED_DUE_TO_DEPENDENCY_FAILURE,
        #                                        PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG]:
        #        all_requested_done = False
        #        break
        # if all_requested_done:
        #    final_batch_status = # Determine BatchStatus.COMPLETED, PARTIALLY_COMPLETED, FAILED
        #    await self.repo.update_batch_status(batch_id, final_batch_status)
             # Publish final EnhancedProcessingUpdate for batch lifecycle completion
        pass

# --- EssayLifecycleService (ELS) ---
# Owns ProcessedEssay entities and their common.models.enums.EssayStatus
class EssayLifecycleService:
    def __init__(self, event_bus_client: EventBusClient, db_repo: Any, # ProcessedEssayRepository
                 content_retrieval_service_client: Any):
        self.bus = event_bus_client
        self.repo = db_repo
        self.content_client = content_retrieval_service_client # For fetching text
        self.service_name = "essay-lifecycle-service"

    async def handle_initiate_pipeline_for_batch_essays(
        self, 
        event_envelope_dict: Dict[str, Any], # Consumes BS's InitiatePipelineForBatchDataV1
        correlation_id: Optional[UUID] = None
    ) -> None:
        # event_data = InitiatePipelineForBatchDataV1.model_validate(event_envelope_dict["data"])
        # batch_ref = event_data.entity_ref
        # essays_to_process = event_data.pipeline_initiation_details.get("essays_to_process", [])
        # target_pipeline_name = event_data.pipeline_initiation_details.get("target_pipeline_name") # e.g. "SPELLCHECK"
        # batch_context_for_ss = event_data.pipeline_initiation_details.get("batch_context_for_ss", {}) # e.g. course_code etc for AI

        # for essay_info in essays_to_process:
        #    essay_id = essay_info.get("essay_id")
        #    current_text_storage_id = essay_info.get("current_text_storage_id")
            
            # Fetch ProcessedEssay from DB
            # essay_db_record = await self.repo.get_essay_by_id(essay_id)
            # student_name = essay_db_record.get("student_name") # Example

            # Determine next EssayStatus based on target_pipeline_name
            # next_essay_status: EssayStatus
            # if target_pipeline_name == "SPELLCHECK":
            #    next_essay_status = EssayStatus.AWAITING_SPELLCHECK
            # elif target_pipeline_name == "AI_FEEDBACK":
            #    next_essay_status = EssayStatus.AWAITING_AI_FEEDBACK
            # ... and so on

            # await self.repo.update_essay_status(essay_id, next_essay_status.value)

            # Prepare context for the specialized service
            # input_context_for_ss = dict(batch_context_for_ss) # Start with batch context
            # input_context_for_ss["student_name"] = student_name # Add essay-specific

            # Construct RequestProcessingForEssayDataV1
            # from common.models.metadata_models import EntityReference, SystemProcessingMetadata
            # from common.models.enums import ProcessingEvent
            # essay_entity_ref = EntityReference(entity_id=str(essay_id), entity_type="essay", parent_id=str(batch_ref.entity_id))
            # sys_meta = SystemProcessingMetadata(entity=essay_entity_ref, event=ProcessingEvent.PROCESSING_STARTED.name)
            # processing_details = {
            #    "text_storage_id": current_text_storage_id,
            #    "correlating_batch_ref_dict": batch_ref.model_dump(mode='json'),
            #    "input_context_for_ss": input_context_for_ss,
            #    "target_pipeline_name_for_ss": target_pipeline_name 
            # }
            # event_data_for_ss = RequestProcessingForEssayDataV1(
            #    event=ProcessingEvent.PROCESSING_STARTED.name, # Or specific e.g., ESSAY_SPELLCHECK_REQUESTED
            #    entity_ref=essay_entity_ref,
            #    status=next_essay_status.value,
            #    system_metadata=sys_meta,
            #    essay_processing_request_details=processing_details
            # )
            
            # Determine topic for the specialized service based on target_pipeline_name
            # target_topic = f"ss.{target_pipeline_name.lower()}.request_processing.v1"
            # target_event_type_str = f"huleedu.ss.{target_pipeline_name.lower()}.request.v1"

            # await publish_event(self.bus, target_topic, event_data_for_ss, 
            #                     target_event_type_str, self.service_name, 
            #                     str(correlation_id) if correlation_id else None)
        pass

    async def handle_specialized_service_essay_result(
        self, 
        event_envelope_dict: Dict[str, Any], # Consumes SS's result (e.g. EssaySpellcheckResultDataV1)
        correlation_id: Optional[UUID] = None
    ) -> None:
        # This method is crucial. It consumes results from SpellChecker, NLP, AI Feedback, etc.
        # event_type = event_envelope_dict.get("event_type")
        # data_dict = event_envelope_dict.get("data", {})
        
        # Based on event_type, parse data_dict into the specific Pydantic model 
        # (e.g., EssaySpellcheckResultDataV1, EssayAIFeedbackResultDataV1)
        
        # Example for Spellcheck result:
        # if "spellcheck_concluded" in event_type:
        #    result_data = EssaySpellcheckResultDataV1.model_validate(data_dict)
        #    essay_id = result_data.entity_ref.entity_id
        #    new_essay_status_from_ss = EssayStatus(result_data.status) # e.g. SPELLCHECKED_SUCCESS

        #    await self.repo.update_essay_status_and_artifacts(
        #        essay_id, 
        #        new_essay_status_from_ss.value,
        #        storage_metadata_dict=result_data.storage_metadata.model_dump(mode='json') if result_data.storage_metadata else None,
        #        specialized_output_dict=result_data.result_summary # Or more specific metadata
        #    )

            # Publish EssayLifecycleStateUpdatedDataV1
            # from common.models.metadata_models import EntityReference, SystemProcessingMetadata
            # from common.models.enums import ProcessingEvent
            # essay_entity_ref = result_data.entity_ref
            # sys_meta = SystemProcessingMetadata(entity=essay_entity_ref, event=ProcessingEvent.ESSAY_LIFECYCLE_STATE_UPDATED.name)
            # update_details = {
            #     "pipeline_step_completed": "SPELLCHECK", # Example
            #     "outcome_status_from_ss": new_essay_status_from_ss.value
            # }
            # lifecycle_event_data = EssayLifecycleStateUpdatedDataV1(
            #     event=ProcessingEvent.ESSAY_LIFECYCLE_STATE_UPDATED.name,
            #     entity_ref=essay_entity_ref,
            #     status=new_essay_status_from_ss.value, # Reflects the new state of the essay
            #     system_metadata=sys_meta,
            #     essay_update_details=update_details
            # )
            # await publish_event(self.bus, f"els.essay.state_updated.{essay_id}.v1",
            #                     lifecycle_event_data, "huleedu.els.essay_state_updated.v1",
            #                     self.service_name, str(correlation_id) if correlation_id else None)
        pass

# --- Specialized Service Example: SpellCheckerService (SS_Spell) ---
class SpellCheckerService:
    def __init__(self, event_bus_client: EventBusClient, content_retrieval_client: Any):
        self.bus = event_bus_client
        self.content_client = content_retrieval_client
        self.service_name = "spellchecker-service"

    async def handle_request_spellcheck_for_essay(
        self, 
        event_envelope_dict: Dict[str, Any], # Consumes ELS's RequestProcessingForEssayDataV1 (subset)
        correlation_id: Optional[UUID] = None
    ) -> None:
        # request_data = RequestProcessingForEssayDataV1.model_validate(event_envelope_dict["data"])
        # essay_ref = request_data.entity_ref
        # text_storage_id = request_data.essay_processing_request_details.get("text_storage_id")
        # batch_ref_dict = request_data.essay_processing_request_details.get("correlating_batch_ref_dict")
        
        # try:
            # 1. Fetch text using self.content_client.get_content(text_storage_id)
            # original_text = await self.content_client.get_text(text_storage_id)
            
            # 2. Perform spell check
            # corrected_text, corrections_summary = perform_spell_check_logic(original_text) # Your logic
            
            # 3. Store corrected_text (gets corrected_text_storage_id)
            #    Store corrections_summary/diff (gets diff_log_storage_id)
            # corrected_text_storage_id = await self.content_client.store_text(corrected_text, "corrected_text")
            # diff_log_storage_id = await self.content_client.store_json(corrections_summary, "spellcheck_log")

            # 4. Publish ESSAY_SPELLCHECK_CONCLUDED_V1 (success)
            # from common.models.metadata_models import EntityReference, SystemProcessingMetadata, StorageReferenceMetadata
            # from common.models.enums import ProcessingEvent, EssayStatus, ContentType
            # sys_meta = SystemProcessingMetadata(entity=essay_ref, event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.name) # Or ESSAY_PROCESSING_COMPLETED
            # storage_meta = StorageReferenceMetadata(references={})
            # storage_meta.add_reference(ContentType.CORRECTED_TEXT, corrected_text_storage_id, f"essays/{essay_ref.entity_id}/corrected.txt")
            # storage_meta.add_reference(ContentType.PROCESSING_LOG, diff_log_storage_id, f"essays/{essay_ref.entity_id}/spellcheck_log.json")
            
            # result_summary_dict = {"corrections_made": len(corrections_summary.get("changes",[]))}
            
            # event_data = EssaySpellcheckResultDataV1(
            #    event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.name,
            #    entity_ref=essay_ref,
            #    status=EssayStatus.SPELLCHECKED_SUCCESS.value,
            #    system_metadata=sys_meta,
            #    storage_metadata=storage_meta,
            #    result_summary=result_summary_dict
            # )
            # await publish_event(self.bus, f"ss.spellcheck.result.{essay_ref.entity_id}.v1", 
            #                     event_data, "huleedu.spellcheck.result_received.v1",
            #                     self.service_name, str(correlation_id) if correlation_id else None)
        # except Exception as e:
            # Publish ESSAY_SPELLCHECK_CONCLUDED_V1 (failure)
            # from common.models.error_info_model import ErrorInfoModel
            # from common.models.enums import ErrorCode
            # error_info = ErrorInfoModel.from_exception(e, ErrorCode.SPELLCHECK_SERVICE_ERROR, "Spell check failed")
            # sys_meta = SystemProcessingMetadata(entity=essay_ref, event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.name, error_info=error_info.model_dump(mode='json'))
            # event_data = EssaySpellcheckResultDataV1(
            #    event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.name, # Still a result, but a failure
            #    entity_ref=essay_ref,
            #    status=EssayStatus.SPELLCHECK_FAILED.value, # Use specific failed status
            #    system_metadata=sys_meta
            # )
            # await publish_event(...)
        pass

# --- AI Feedback Service (SS_AI) - partial example ---
class AIFeedbackService:
    def __init__(self, event_bus_client: EventBusClient, content_retrieval_client: Any, llm_client: Any):
        self.bus = event_bus_client
        self.content_client = content_retrieval_client
        self.llm_client = llm_client # For actual AI calls
        self.service_name = "ai-feedback-service"

    async def handle_request_ai_feedback_for_essay(
        self, 
        event_envelope_dict: Dict[str, Any], # Consumes ELS's RequestProcessingForEssayDataV1 (subset for AI)
        correlation_id: Optional[UUID] = None
    ) -> None:
        # request_data = RequestProcessingForEssayDataV1.model_validate(event_envelope_dict["data"])
        # essay_ref = request_data.entity_ref
        # details = request_data.essay_processing_request_details
        # text_storage_id = details.get("text_for_ai_storage_id")
        # nlp_metrics_storage_id = details.get("nlp_metrics_storage_id") # May be optional
        # input_context = details.get("ai_feedback_input_context", {}) # course_code, instructions, student_name etc.

        # try:
            # 1. Fetch text (e.g., corrected_text) using self.content_client
            # essay_text = await self.content_client.get_text(text_storage_id)
            # nlp_metrics = None
            # if nlp_metrics_storage_id:
            #    nlp_metrics = await self.content_client.get_json(nlp_metrics_storage_id)

            # 2. Prepare prompts using essay_text, nlp_metrics (if avail), and input_context
            # (course_code, essay_instructions, student_name, class_designation, teacher_name)
            # prompt_for_feedback = self._build_feedback_prompt(essay_text, input_context, nlp_metrics)
            # prompt_for_revision = self._build_revision_prompt(essay_text, input_context, nlp_metrics) # if doing editor revision

            # 3. Call LLM for feedback and/or revision
            # ai_feedback_llm_output = await self.llm_client.generate(prompt_for_feedback)
            # ai_revision_llm_output = await self.llm_client.generate(prompt_for_revision) # if applicable

            # 4. Parse LLM outputs, extract metrics, feedback text, revision text
            # generated_feedback_text = parse_feedback(ai_feedback_llm_output)
            # generated_revision_text = parse_revision(ai_revision_llm_output)
            # ai_computed_metrics = extract_ai_metrics(ai_feedback_llm_output) # word_count, model_used etc.
            
            # 5. Store artifacts
            # feedback_text_storage_id = await self.content_client.store_text(generated_feedback_text, "ai_feedback")
            # revision_text_storage_id = await self.content_client.store_text(generated_revision_text, "ai_revision")
            # detailed_analysis_storage_id = await self.content_client.store_json(ai_computed_metrics, "ai_analysis_detail")

            # 6. Construct AIFeedbackMetadata
            # from common.models.metadata_models import AIFeedbackMetadata
            # ai_meta_output = AIFeedbackMetadata(
            #    teacher_name=input_context.get("teacher_name"), # Copied from input context
            #    course_code=input_context.get("course_code"),
            #    essay_instructions=input_context.get("essay_instructions"),
            #    class_designation=input_context.get("class_designation"),
            #    student_name=input_context.get("student_name"),
            #    word_count=ai_computed_metrics.get("word_count_processed_by_ai"),
            #    model_version=ai_computed_metrics.get("model_version_used"),
            #    # ... other fields from AIFeedbackMetadata like readability_metrics, language_metrics ...
            #    has_feedback=True,
            #    has_editor_revision=bool(generated_revision_text),
            #    has_metrics=True 
            # )

            # 7. Publish ESSAY_AI_FEEDBACK_CONCLUDED_V1 (success)
            # from common.models.metadata_models import SystemProcessingMetadata, StorageReferenceMetadata
            # from common.models.enums import ProcessingEvent, EssayStatus, ContentType
            # sys_meta = SystemProcessingMetadata(entity=essay_ref, event=ProcessingEvent.ESSAY_AIFEEDBACK_RESULT_RECEIVED.name)
            # storage_meta = StorageReferenceMetadata(references={})
            # storage_meta.add_reference(ContentType.STUDENT_FACING_AI_FEEDBACK_TEXT, feedback_text_storage_id, ...)
            # storage_meta.add_reference(ContentType.AI_EDITOR_REVISION_TEXT, revision_text_storage_id, ...)
            # storage_meta.add_reference(ContentType.AI_DETAILED_ANALYSIS_JSON, detailed_analysis_storage_id, ...)

            # event_data = EssayAIFeedbackResultDataV1(
            #    event=ProcessingEvent.ESSAY_AIFEEDBACK_RESULT_RECEIVED.name,
            #    entity_ref=essay_ref,
            #    status=EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS.value,
            #    system_metadata=sys_meta,
            #    ai_feedback_metadata=ai_meta_output,
            #    storage_metadata=storage_meta
            # )
            # await publish_event(self.bus, f"ss.aifeedback.result.{essay_ref.entity_id}.v1",
            #                     event_data, "huleedu.aifeedback.result_received.v1",
            #                     self.service_name, str(correlation_id) if correlation_id else None)
        # except Exception as e:
            # Publish failure event similarly...
        pass
```

---
**3. Event Flow Walkthrough Summary (Using the Above Structures)**

1.  **Batch Configured**: User/System configures a `BatchUpload` (ID: B1) with `requested_pipelines = ["SPELLCHECK", "AI_FEEDBACK"]`. BS updates `BatchUpload.status` to `PENDING_PROCESSING_INITIATION` and its `processing_pipeline_state` accordingly. Publishes `BATCH_STATUS_UPDATED_V1` (payload is `EnhancedProcessingUpdateEventData`) and `BATCH_PIPELINE_PROGRESS_UPDATED_V1` (payload is `BatchPipelineProgressUpdatedDataV1` with `ProcessingPipelineState` snapshot).
2.  **User Starts Processing**: `POST /v1/batches/B1/start-processing`.
3.  **BS Initiates SpellCheck Phase**:
    * Sets `BatchUpload.status` to `PROCESSING`. Updates `processing_pipeline_state.spellcheck.status` to `DISPATCH_INITIATED`.
    * Publishes `BATCH_PROCESSING_STARTED_V1` (`EnhancedProcessingUpdateEventData`).
    * Publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1` (`BatchPipelineProgressUpdatedDataV1`).
    * Publishes `INITIATE_PIPELINE_FOR_BATCH_V1` (payload `InitiatePipelineForBatchDataV1` with `target_pipeline_name="SPELLCHECK"`, list of essays E1,E2 from B1 with original text refs, and NO specific batch context beyond IDs as SpellChecker doesn't need course_code etc.).
4.  **ELS Receives, Dispatches to SpellChecker**:
    * For E1: ELS updates `ProcessedEssay.status` to `AWAITING_SPELLCHECK`. Publishes `REQUEST_PROCESSING_FOR_ESSAY_V1` (payload `RequestProcessingForEssayDataV1` for SpellChecker with essay_ref E1, status `AWAITING_SPELLCHECK`, details including text_storage_id).
5.  **SpellChecker Processes E1**:
    * Fetches text for E1. Corrects it. Stores corrected text (ref_E1_corr) and log.
    * Publishes `ESSAY_SPELLCHECK_CONCLUDED_V1` (payload `EssaySpellcheckResultDataV1` for E1, status `SPELLCHECKED_SUCCESS`, storage_meta with ref_E1_corr).
6.  **ELS Receives SpellCheck Result for E1**:
    * Updates `ProcessedEssay E1.status` to `SPELLCHECKED_SUCCESS`. Stores ref_E1_corr.
    * Publishes `ESSAY_LIFECYCLE_STATE_UPDATED_V1` (payload `EssayLifecycleStateUpdatedDataV1` for E1, status `SPELLCHECKED_SUCCESS`).
7.  **BS Receives E1 SpellCheck Update**:
    * Updates `processing_pipeline_state.spellcheck.essay_counts` for B1.
    * Publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.
    * *(Repeats 4-7 for E2)*
8.  **BS: All Essays SpellChecked for Batch B1**:
    * `processing_pipeline_state.spellcheck.status` -> `COMPLETED_SUCCESSFULLY`.
    * BS checks dependencies for next requested pipeline: "AI_FEEDBACK". Dependencies (SpellCheck done) are met.
    * Updates `processing_pipeline_state.ai_feedback.status` to `DISPATCH_INITIATED`.
    * Publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.
    * Publishes `INITIATE_PIPELINE_FOR_BATCH_V1` (payload `InitiatePipelineForBatchDataV1` with `target_pipeline_name="AI_FEEDBACK"`, list of essays E1,E2 with *corrected text refs*, and this time the `pipeline_initiation_details` will contain the `batch_context_for_ai` (course_code, instructions, teacher_name etc. from `BatchProcessingMetadata` of B1)).
9.  **ELS Receives, Dispatches to AI Feedback Service**:
    * For E1: ELS updates `ProcessedEssay.status` to `AWAITING_AI_FEEDBACK`. Publishes `REQUEST_PROCESSING_FOR_ESSAY_V1` (payload `RequestProcessingForEssayDataV1` targeting AI Feedback, with `essay_processing_request_details` containing corrected text ref, NLP metrics ref (if available), and the crucial `ai_feedback_input_context` assembled by ELS).
10. **AI Feedback Service Processes E1**:
    * Fetches text. Uses `ai_feedback_input_context`. Generates feedback. Stores artifacts.
    * Publishes `ESSAY_AI_FEEDBACK_CONCLUDED_V1` (payload `EssayAIFeedbackResultDataV1` for E1, status `AI_FEEDBACK_COMPLETED_SUCCESS`, full `AIFeedbackMetadata` (including copied input context), `StorageReferenceMetadata`).
11. **ELS Receives AI Feedback Result for E1**:
    * Updates `ProcessedEssay E1.status` to `AI_FEEDBACK_COMPLETED_SUCCESS`. Stores `AIFeedbackMetadata` and artifact refs.
    * Publishes `ESSAY_LIFECYCLE_STATE_UPDATED_V1`.
12. **BS Receives E1 AI Feedback Update**:
    * Updates `processing_pipeline_state.ai_feedback.essay_counts`.
    * Publishes `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.
    * *(Repeats 10-12 for E2)*
13. **BS: All Essays AI Feedback Done for Batch B1**:
    * `processing_pipeline_state.ai_feedback.status` -> `COMPLETED_SUCCESSFULLY`.
    * BS checks if any more `requested_pipelines` for B1. If not:
        * Sets `BatchUpload B1.status` to `BatchStatus.COMPLETED.value`.
        * Publishes `BATCH_LIFECYCLE_COMPLETED_V1` (`EnhancedProcessingUpdateEventData`).
        * Publishes final `BATCH_PIPELINE_PROGRESS_UPDATED_V1`.

---
**4. Impact on Other System Components & Refactoring**

* **UI**: Will subscribe via WebSockets (to the Notification Service) to topics like `batch.progress.{batch_id}.updated.v1` and `els.essay.state_updated.{essay_id}.v1`. It will receive `ProcessingPipelineState` snapshots and detailed essay status updates to render rich, live progress views.
* **Notification Service**: Becomes a critical hub for distributing these granular progress events to the UI.
* **User/Auth Service**: Interacts with BS during batch creation to associate `user_id` (teacher).
* **File Upload Service**: Needs to create initial `BatchUpload` and `ProcessedEssay` records (perhaps by publishing events that BS and ELS consume to create these entities in their respective databases) and store the initial essay texts, providing the first `storage_id`.
* **Database Design**:
    * BS needs `BatchUpload` table with `status` (from `BatchStatus`) and `processing_metadata` (JSONB for `ProcessingPipelineState`).
    * ELS needs `ProcessedEssay` table with `status` (from extended `EssayStatus`), `batch_id` (FK), and `content_metadata` (JSONB for storing results like `AIFeedbackMetadata` dict, NLP output dict, artifact references).
    * Specialized Services will have their own DBs for internal job tracking, caching, etc. They will not share tables with BS/ELS.
* **Refactoring Effort**:
    * This requires defining the new Pydantic event data models (e.g., `InitiatePipelineForBatchDataV1`, `RequestProcessingForEssayDataV1`, `EssaySpellcheckResultDataV1`, `BatchPipelineProgressUpdatedDataV1`, etc.) in your common library.
    * Implementing the `ProcessingPipelineState` model and its associated sub-phase enums.
    * Building out the orchestration logic in BS to manage `ProcessingPipelineState` and publish events.
    * Building out ELS to manage `ProcessedEssay` states and act as an intermediary.
    * Adapting all Specialized Services to use the new event contracts and consume the targeted input context provided by ELS.
    * Extensive work on the `common/models/enums.py` to add new specific statuses for `EssayStatus` and potentially a few for `BatchStatus` and `ProcessingEvent`.
