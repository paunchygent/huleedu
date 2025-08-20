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
  * **Values**: `AWAITING_CONTENT_VALIDATION`, `PROCESSING_PIPELINES`, `COMPLETED_SUCCESSFULLY`, `COMPLETED_WITH_FAILURES`, etc.
  * **Role**: Provides a summary view of where the batch stands. BOS updates this based on major milestones.

* **`ProcessingPipelineState` & `PipelineStateDetail` Models**:
  * **Role**: These models are managed by BOS to track the detailed progress of *each specific pipeline* requested for a batch.
  * `ProcessingPipelineState` contains a field for each known pipeline type (e.g., `spellcheck`, `cj_assessment`), holding a `PipelineStateDetail` instance.
  * `PipelineStateDetail` contains the `status` (e.g., `IN_PROGRESS`, `COMPLETED_SUCCESSFULLY`), `essay_counts`, and timestamps for that specific pipeline.

### 2. Essay Lifecycle Management (Managed by ELS)

The Essay Lifecycle Service (ELS) manages the state of individual essays as they progress through a *specific pipeline commanded by BOS*.

* **`EssayStatus` Enum**: Defines the state of an individual essay *within the context of the currently active pipeline*.
  * **Values**: `READY_FOR_PROCESSING`, `AWAITING_SPELLCHECK`, `SPELLCHECK_SUCCESS`, `AWAITING_CJ_ASSESSMENT`, etc.
  * **Role**: Allows ELS to precisely track and act upon the state of each essay for the pipeline it's currently executing based on a BOS command.

### 3. Eventing Framework & Metadata

* **`EventEnvelope` Model**: The standard wrapper for all asynchronous messages published to Kafka. It provides common metadata fields like `event_id`, `event_type`, `source_service`, and `correlation_id`.

* **`ProcessingEvent` Enum**: Provides semantic names for specific business occurrences (e.g., `SPELLCHECK_PHASE_COMPLETED`, `SPELLCHECK_RESULTS`). These are mapped to Kafka topic names via the `topic_name()` function.

### 4. Key Data Payload Models for Orchestration

These Pydantic models define the `data` field within the `EventEnvelope` for specific interactions.

* **Coordination Events (File Service -> ELS & ELS -> BOS)**:
  * `BatchEssaysRegistered`: Published by BOS to ELS to define the "slots" for a new batch.
  * `EssayContentProvisionedV1`: Published by File Service when an essay's text is successfully extracted and stored.
  * `EssayValidationFailedV1`: Published by File Service when a file fails validation; critical for preventing pipeline stalls.
  * `BatchEssaysReady`: Published by ELS to BOS once all expected content for a batch has been accounted for (either provisioned or failed).

* **Command Models (BOS -> ELS)**: Define what BOS sends to ELS to initiate a pipeline for a batch.
  * Example: `BatchServiceCJAssessmentInitiateCommandDataV1` contains the list of essays to process and context like language and instructions.

* **Request Models (ELS -> Specialized Services)**: Define what ELS sends to a specialized service for an individual essay.
  * Example: `EssayLifecycleSpellcheckRequestV1` includes the `text_storage_id` and language for the spell checker.

* **Result Models (Specialized Services -> ELS)**: Define what specialized services send back to ELS.
  * Example: `SpellcheckResultDataV1` includes the outcome status and a reference to the corrected text.

* **Phase Outcome Event (ELS -> BOS - CRITICAL)**:
  * `ELSBatchPhaseOutcomeV1`: This is the key event that enables dynamic pipeline orchestration. ELS publishes this to BOS after an entire batch has completed a phase (e.g., spellcheck). It contains the list of successfully processed essays and their *new* output `text_storage_id`s, which BOS needs to command the next phase.

---

## 🧩 Typical Processing Flow Example: SPELLCHECK_PIPELINE

This illustrates how the `common_core` components are used in a typical (happy path) pipeline.

1. **BOS: Initiate Batch & First Pipeline (SPELLCHECK\_PIPELINE)**
    * A batch is registered, and BOS waits for ELS. Upon receiving `BatchEssaysReady`, BOS decides to start the "spellcheck" pipeline.
    * **BOS Internal State**: Updates `ProcessingPipelineState.spellcheck.status` to `IN_PROGRESS`.
    * **BOS Publishes Command to ELS**:
        * `EventEnvelope` with `event_type = "huleedu.els.spellcheck.initiate.command.v1"`.
        * `data = BatchServiceSpellcheckInitiateCommandDataV1(...)` including the list of essays to process.

2. **ELS: Process Command, Dispatch to SCS**
    * Receives command from BOS.
    * For each essay, transitions its `EssayStatus` to `AWAITING_SPELLCHECK`.
    * **ELS Publishes Request to SCS**:
        * `EventEnvelope` with `event_type = "huleedu.essay.spellcheck.requested.v1"`.
        * `data = EssayLifecycleSpellcheckRequestV1(...)`.
    * ELS then transitions the essay's `EssayStatus` to `SPELLCHECK_IN_PROGRESS`.

3. **SCS: Process Essay, Report Result to ELS**
    * Receives request from ELS. Performs spellcheck.
    * **SCS Publishes Result to ELS**:
        * `EventEnvelope` with `event_type = "huleedu.essay.spellcheck.completed.v1"`.
        * `data = SpellcheckResultDataV1(...)` with `status = EssayStatus.SPELLCHECK_SUCCESS` and the new `storage_id` for the corrected text.

4. **ELS: Process Result, Aggregate for Batch**
    * Receives result from SCS and updates the individual essay's `EssayStatus` to `SPELLCHECK_SUCCESS`.
    * ELS tracks the status for all essays commanded for the spellcheck phase.

5. **ELS: Publish Phase Outcome to BOS (CRITICAL STEP)**
    * Once all essays in the batch have completed the spellcheck phase, ELS aggregates the results.
    * **ELS Publishes Phase Outcome to BOS**:
        * `EventEnvelope` with `event_type = "huleedu.els.batch_phase.outcome.v1"`.
        * `data = ELSBatchPhaseOutcomeV1(...)` containing:
            * `phase_name = "spellcheck"`
            * `phase_status = "COMPLETED_SUCCESSFULLY"`
            * `processed_essays = [EssayProcessingInputRefV1(essay_id="A", text_storage_id="corrected_A_id"), ...]` (list of successful essays with their **new** text storage IDs).
            * `failed_essay_ids = [...]`

6. **BOS: Process Conclusion, Initiate Next Pipeline (e.g., CJ\_PIPELINE)**
    * Receives `ELSBatchPhaseOutcomeV1` from ELS.
    * **BOS Internal State**:
        * Updates `ProcessingPipelineState.spellcheck.status` to `COMPLETED_SUCCESSFULLY`.
        * Identifies the next pipeline (e.g., "cj_assessment") and updates its status to `IN_PROGRESS`.
    * **BOS Publishes Command to ELS** for the next phase, using the `output_storage_id`s from the `ELSBatchPhaseOutcomeV1` event as the inputs for the new command.

This cycle repeats for all `requested_pipelines`. When the last pipeline concludes, BOS sets a final `BatchStatus` (e.g., `COMPLETED_SUCCESSFULLY`) and can publish a final notification.

---

## 🧱 Structure of `common_core` Package

The source code for `common_core` is organized under `src/common_core/` with subdirectories for `events/` and key modules for `enums.py`, `metadata_models.py`, `pipeline_models.py`, `batch_service_models.py`, and `essay_service_models.py`. The `__init__.py` handles exports and Pydantic model rebuilding.

### ⚙️ Usage by Services

All services depend on `common_core` for contracts and shared definitions.

* **Model Rebuilding**: The main `__init__.py` explicitly calls `model_rebuild(raise_errors=True)` on Pydantic models to ensure correct resolution of forward references.

---

## 🔧 Development and Maintenance

Changes to this package must be handled with extreme care as they affect all other services. All contract tests must pass before merging changes.
