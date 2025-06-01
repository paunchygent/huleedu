# HuleEdu Common Core (`huleedu-common-core`)

## 🎯 Purpose

The **HuleEdu Common Core** package is the definitive source for shared data contracts, enumerations, and essential metadata models utilized across all microservices within the HuleEdu ecosystem. Its primary objective is to ensure consistency, type safety, and clearly defined interfaces for inter-service communication, particularly in the event-driven orchestration flows.

This package enables:

* Consistent data structures for events, commands, and API payloads.
* Reduced redundancy and a single source of truth for shared definitions.
* Simplified integration between services.
* A stable foundation for the platform's event-driven architecture.

---

## 📦 Core Components & Their Roles in Orchestration

Understanding these `common_core` components is key to developing services that integrate correctly within the HuleEdu processing flows.

### 1. Overall Orchestration State (Managed by BOS)

The Batch Orchestrator Service (BOS) manages the overall lifecycle of a batch and the sequence of processing pipelines applied to it.

* **`BatchStatus` Enum**: Defines the high-level lifecycle stage of an entire batch entity.
  * **Values (as refined)**: [This reflects our latest discussion; ensure `enums.py` is updated accordingly]
    * `AWAITING_CONTENT_INGESTION`: Batch defined; content being ingested/validated.
    * `CONTENT_INGESTION_FAILED`: Critical failure during initial content ingestion. (Terminal for this path)
    * `AWAITING_PIPELINE_CONFIGURATION`: Content successfully ingested; awaiting user to define/confirm processing pipelines.
    * `READY_FOR_PIPELINE_EXECUTION`: Pipelines configured; batch queued for BOS to start the first pipeline.
    * `PROCESSING_PIPELINES`: BOS is actively orchestrating one or more pipelines for the batch.
    * `COMPLETED_SUCCESSFULLY`: All requested pipelines for the batch finished successfully. (Terminal)
    * `COMPLETED_WITH_FAILURES`: All requested pipelines finished, but with some non-critical essay/pipeline failures. (Terminal)
    * `FAILED_CRITICALLY`: A critical failure stopped batch processing. (Terminal)
    * `CANCELLED`: Batch processing was explicitly cancelled. (Terminal)
  * **Role**: Provides a summary view of where the batch stands. BOS updates this based on major milestones.

* **`ProcessingPipelineState` & `PipelineStateDetail` Models**:
  * **Role**: These models are managed by BOS to track the detailed progress of *each specific pipeline* requested for a batch.
  * `ProcessingPipelineState` contains:
    * `batch_id: str`
    * `requested_pipelines: List[str]` (e.g., `["SP_PIPELINE", "CJ_PIPELINE"]`)
    * Fields for each known pipeline type, holding a `PipelineStateDetail` instance (e.g., `spellcheck: Optional[PipelineStateDetail]`).
  * `PipelineStateDetail` contains:
    * `status: PipelineExecutionStatus` (e.g., `IN_PROGRESS`, `COMPLETED_SUCCESSFULLY` for *that specific pipeline* within the batch).
    * `essay_counts: EssayProcessingCounts` (total, successful, failed essays *for that pipeline*).
    * Timestamps (`started_at`, `completed_at`).

### 2. Essay Lifecycle Management (Managed by ELS)

The Essay Lifecycle Service (ELS) manages the state of individual essays as they progress through a *specific pipeline commanded by BOS*.

* **`EssayStatus` Enum**: Defines the state of an individual essay *within the context of the currently active pipeline* ELS is managing for it.
  * **Values for Walking Skeleton (SPELLCHECK & CJ_ASSESSMENT pipelines - as refined)**: [Ensure `enums.py` is updated]
    * `CONTENT_INGESTED`: Essay content ingested and validated by upstream "File Service"/initial steps; known to ELS.
    * `CONTENT_INGESTION_FAILED`: Initial ingestion/validation failed for this essay.
    * `AWAITING_SPELLCHECK`, `SPELLCHECK_IN_PROGRESS`, `SPELLCHECK_SUCCESS`, `SPELLCHECK_FAILED`
    * `AWAITING_CJ_ASSESSMENT`, `CJ_ASSESSMENT_IN_PROGRESS`, `CJ_ASSESSMENT_SUCCESS`, `CJ_ASSESSMENT_FAILED`
    * `ESSAY_PIPELINE_CRITICAL_FAILURE`: ELS encountered an unrecoverable issue orchestrating this essay for its current pipeline.
  * **Role**: Allows ELS to precisely track and act upon the state of each essay for the pipeline it's currently executing based on a BOS command.

### 3. Eventing Framework & Metadata

* **`EventEnvelope` Model**: The standard wrapper for all asynchronous messages (events, commands, results) published to Kafka. It provides common metadata fields.
  * Key fields: `event_id`, `event_type` (e.g., `"huleedu.bos.spellcheck.initiate_command.v1"`), `event_timestamp`, `source_service`, `correlation_id`, `data` (the specific payload).

* **`ProcessingEvent` Enum**: Provides semantic names for specific business occurrences or message types, typically used in the `event_name` field of data payloads that inherit from `BaseEventData`.
  * **Refinement Note**: Consider standardizing terminal batch lifecycle events to a single `BATCH_LIFECYCLE_CONCLUDED`, with the specific outcome (`BatchStatus`) in the payload.

* **`ProcessingStage` Enum**: Generic lifecycle stages (`PENDING`, `INITIALIZED`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`).
  * **Role**: Used within `SystemProcessingMetadata.processing_stage` to give a high-level status to the operation or entity an event pertains to (e.g., an SCS result indicating its spellcheck task `COMPLETED`).

* **`SystemProcessingMetadata` Model**: Embedded in many event data models to provide context about the processing operation related to the event.

### 4. Key Data Payload Models for Orchestration

These Pydantic models define the `data` field within the `EventEnvelope` for specific interactions.

* **Command Models (BOS -> ELS)**: Define what BOS sends to ELS to initiate a pipeline for a batch.
  * Example: `BatchServiceSpellcheckInitiateCommandDataV1`
    * `event_name`: `ProcessingEvent.ESSAY_PHASE_INITIATION_REQUESTED`
    * `entity_ref`: Identifies the batch.
    * `essays_to_process: List[EssayProcessingInputRefV1]`: Contains `essay_id` and input `text_storage_id` for each essay.
    * Pipeline-specific metadata (e.g., `language`).
    * *(Refinement based on discussion): Should include the initial `EssayStatus` ELS must set, e.g., `initial_essay_status: EssayStatus`.*
  * Similar models exist/will exist for CJ Assessment, NLP, etc. (e.g., `BatchServiceCJAssessmentInitiateCommandDataV1`).

* **Request Models (ELS -> Specialized Services)**: Define what ELS sends to a specialized service for an individual essay.
  * Example: `EssayLifecycleSpellcheckRequestV1` (inherits `ProcessingUpdate`)
    * `event_name`: `ProcessingEvent.ESSAY_LIFECYCLE_SPELLCHECK_REQUESTED`
    * `entity_ref`: Identifies the essay (and its parent batch).
    * `status`: The current `EssayStatus` (e.g., `AWAITING_SPELLCHECK`).
    * `system_metadata`: Includes `processing_stage` (e.g., `PENDING`).
    * `text_storage_id`, `language` (for multilingual spell checking support).

* **Result Models (Specialized Services -> ELS)**: Define what specialized services send back to ELS.
  * Example: `SpellcheckResultDataV1` (inherits `ProcessingUpdate`)
    * `event_name`: `ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED`
    * `entity_ref`: Identifies the essay.
    * `status`: The outcome `EssayStatus` (e.g., `SPELLCHECK_SUCCESS`).
    * `system_metadata`: Includes `processing_stage` (e.g., `COMPLETED`).
    * `original_text_storage_id`, `storage_metadata` (with corrected text `storage_id`), `corrections_made`.
  * The new `AIFeedbackResultDataV1` follows this pattern, embedding `AIFeedbackMetadata` and optionally a `feedback_content_storage_id`.

* **ELS to BOS Reporting Event Data (for `batch.phase.concluded.v1`)**:
  * **Role**: ELS uses this to inform BOS that all essays in a batch have been processed for a specific pipeline.
  * **Structure (as a dictionary payload within `EventEnvelope.data`)**:
    * `"event_name"`: `ProcessingEvent.BATCH_PHASE_CONCLUDED.value` (or the string `"batch.phase.concluded.v1"`).
    * `"entity_ref"`: Batch ID.
    * `"phase"`: Name of the pipeline just concluded (e.g., "SP\_PIPELINE").
    * `"details"`: `dict` containing:
      * `successfully_processed_essay_count: int`
      * `failed_essay_count: int`
      * `total_essays_commanded_for_pipeline: int`
      * `processed_essay_outcomes: List[Dict]`: Each dict with `essay_id`, `final_essay_status_for_pipeline` (e.g., `SPELLCHECK_SUCCESS`), `output_storage_id` (crucial for next pipeline), `error_details` (if any).
  * *ELS does NOT determine the overall `PipelineExecutionStatus` for the batch-pipeline; it provides the facts for BOS to make this determination.*

---

## 🧩 Typical Processing Flow Example: SPELLCHECK_PIPELINE

This illustrates how the `common_core` components are used in a typical (happy path) pipeline.

1. **BOS: Initiate Batch & First Pipeline (SPELLCHECK\_PIPELINE)**
    * Batch `batch_123` is created.
    * BOS sets `BatchStatus` to `AWAITING_PIPELINE_CONFIGURATION` (after content ingestion is confirmed ready). User configures `requested_pipelines = ["SP_PIPELINE", "CJ_PIPELINE"]`.
    * BOS updates `BatchStatus` to `READY_FOR_PIPELINE_EXECUTION`.
    * BOS decides to start "SP\_PIPELINE".
    * **BOS Internal State**:
        * Updates `ProcessingPipelineState.spellcheck.status` for `batch_123` to `PipelineExecutionStatus.IN_PROGRESS`.
        * Updates overall `BatchStatus` to `PROCESSING_PIPELINES`.
    * **BOS Publishes Command to ELS**:
        * `EventEnvelope` with `event_type = "huleedu.bos.spellcheck.initiate_command.v1"`.
        * `data = BatchServiceSpellcheckInitiateCommandDataV1(...)` including:
            * `event_name = ProcessingEvent.ESSAY_PHASE_INITIATION_REQUESTED`
            * `essays_to_process = [EssayProcessingInputRefV1(essay_id="A", text_storage_id="orig_A"), ...]`
            * (Payload should also specify initial `EssayStatus`, e.g., `AWAITING_SPELLCHECK`)

2. **ELS: Process Command, Dispatch to SCS**
    * Receives command from BOS.
    * For each essay:
        * **ELS Internal State**: Sets `EssayState.current_status` to `AWAITING_SPELLCHECK`.
        * **ELS Publishes Request to SCS**:
            * `EventEnvelope` with `event_type = "huleedu.essay_lifecycle.spellcheck.request.v1"`.
            * `data = EssayLifecycleSpellcheckRequestV1(...)` including:
                * `event_name = ProcessingEvent.ESSAY_LIFECYCLE_SPELLCHECK_REQUESTED`
                * `entity_ref` for the essay.
                * `status = EssayStatus.AWAITING_SPELLCHECK`
                * `system_metadata.processing_stage = ProcessingStage.PENDING`
                * `text_storage_id` (original text).
                * `language` (for multilingual spell checking support).
        * **ELS Internal State**: Sets `EssayState.current_status` to `SPELLCHECK_IN_PROGRESS`.

3. **SCS: Process Essay, Report Result to ELS**
    * Receives request from ELS. Performs spellcheck.
    * **SCS Publishes Result to ELS**:
        * `EventEnvelope` with `event_type = "huleedu.spellchecker.essay.concluded.v1"`.
        * `data = SpellcheckResultDataV1(...)` including:
            * `event_name = ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED`
            * `entity_ref` for the essay.
            * `status = EssayStatus.SPELLCHECK_SUCCESS`
            * `system_metadata.processing_stage = ProcessingStage.COMPLETED`
            * `storage_metadata` (with corrected text `storage_id`).

4. **ELS: Process Result, Update State, Aggregate for Batch**
    * Receives result from SCS.
    * **ELS Internal State**: For the essay, sets `EssayState.current_status` to `SPELLCHECK_SUCCESS`, stores new `storage_id`.
    * Once all essays in `batch_123` for "SP\_PIPELINE" are processed:
        * **ELS Publishes Batch Phase Conclusion to BOS**:
            * `EventEnvelope` with `event_type = "huleedu.els.batch_phase.concluded.v1"`.
            * `data` (dictionary) including:
                * `event_name = ProcessingEvent.BATCH_PHASE_CONCLUDED.value`
                * `phase = "SP_PIPELINE"`
                * `details = { "successfully_processed_essay_count": ..., "failed_essay_count": ..., "processed_essay_outcomes": [{"essay_id": "A", "final_essay_status_for_pipeline": "SPELLCHECK_SUCCESS", "output_storage_id": "corrected_A_id"}, ...] }`

5. **BOS: Process Conclusion, Initiate Next Pipeline (e.g., CJ\_PIPELINE)**
    * Receives `batch.phase.concluded.v1` from ELS.
    * **BOS Internal State**:
        * Updates `ProcessingPipelineState.spellcheck.status` for `batch_123` to `PipelineExecutionStatus.COMPLETED_SUCCESSFULLY` (based on ELS's `details`).
        * Identifies "CJ\_PIPELINE" as next.
        * Updates `ProcessingPipelineState.cj_assessment.status` to `PipelineExecutionStatus.IN_PROGRESS`.
        * Overall `BatchStatus` remains `PROCESSING_PIPELINES`.
    * **BOS Publishes Command to ELS** for "CJ\_PIPELINE", using the `output_storage_id`s from ELS's previous report as the input `text_storage_id`s for the essays in the new `BatchServiceCJAssessmentInitiateCommandDataV1`.

This cycle repeats for all `requested_pipelines`. When the last pipeline concludes, BOS sets a final `BatchStatus` (e.g., `COMPLETED_SUCCESSFULLY`) and publishes a `BATCH_LIFECYCLE_CONCLUDED` event.

---

## 🧱 Structure of `common_core` Package

(As previously described, listing key files and their purpose - see)
The source code for `common_core` is organized under `src/common_core/` with subdirectories for `events/` and key modules for `enums.py`, `metadata_models.py`, `pipeline_models.py`, `batch_service_models.py`, and `essay_service_models.py`. The `__init__.py` handles exports and Pydantic model rebuilding.

---

### ⚙️ Usage by Services

(As previously described - all services depend on `common_core` for contracts and shared definitions - see)

* **Model Rebuilding**: The main `__init__.py` explicitly calls `model_rebuild(raise_errors=True)` on Pydantic models to ensure correct resolution of forward references.

---

## 🔧 Development and Maintenance

(As previously described - care with changes, run checks, build process - see)
