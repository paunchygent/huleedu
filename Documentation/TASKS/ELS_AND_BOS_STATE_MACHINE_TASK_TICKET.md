# Task Ticket 3: Implement Dynamic Pipeline Orchestration with ELS State Machine

**Ticket ID:** `HULEEDU_PIPELINE_REFACTOR_001`
**Title:** Implement Dynamic Pipeline Orchestration (BOS) & Essay State Machine (ELS)
**Status:** 🔄 **IN PROGRESS** (Phase 2 Complete - Phase 3 Ready)
**Progress:** Phase 1 ✅ | Phase 2 ✅ | Phase 3 🔄 | Phase 4 🔄
**Assignee:**
**Sprint:**
**Story Points:**

## 📊 **CURRENT PROGRESS SUMMARY**

### ✅ **COMPLETED: Phases 1 & 2**

- **Phase 1**: Common core event contracts established (5/5 tests passing)
  - `ALL_PROCESSING_COMPLETED` added to EssayStatus enum
  - `ELSBatchPhaseOutcomeV1` event model created and validated
  - Topic mapping: `huleedu.els.batch_phase.outcome.v1`
  
- **Phase 2**: ELS State Machine implemented (8/8 tests passing)
  - Transitions library integrated (transitions 0.9.2)
  - Formal state machine with all EssayStatus states and transitions
  - StateTransitionValidator enhanced for machine compatibility
  - SQLiteEssayStateStore updated with machine integration
  - Complete validation test suite passing

### 🔄 **IN PROGRESS: Phase 3 & 4 Setup**

- **Phase 3**: BOS Dynamic Pipeline Orchestration (7/8 tests - 1 validation issue)
  - Foundation ready for BOS orchestration enhancements
  - Missing: `essay_ids` field validation in BOS batch registration
  
- **Phase 4**: End-to-End Validation (6/7 tests - 1 integration issue)
  - Test framework established
  - Missing: EventEnvelope integration for complete validation

### 🎯 **REMAINING WORK**

1. **Phase 3**: Complete BOS orchestration with pipeline sequencing
2. **Phase 4**: Final end-to-end validation with multiple pipeline sequences
3. **Clean-up**: Resolve remaining linter issues (MyPy type annotations)

---

## 🚀 **OVERVIEW**

This ticket directs the refactoring of the Essay Lifecycle Service (ELS) to use a formal state machine for managing individual essay statuses and transitions. It also directs enhancements to the Batch Orchestrator Service (BOS) to become the primary owner of defining and orchestrating dynamic "mix and match" processing pipelines for batches. This will involve defining new event contracts in `common_core` for inter-service communication regarding pipeline phase progression.

The goal is to enable flexible pipeline sequences (e.g., Spellcheck -> CJ Assessment; Spellcheck -> AI Feedback -> NLP) orchestrated by BOS, with ELS robustly managing essay states based on commands from BOS and results from specialized services.

## 🎯 **SUB-TASKS & IMPLEMENTATION PLAN**

### **Phase 1: `common_core` Updates for Enhanced Pipeline Communication**

- **Goal:** Define the necessary shared Pydantic models and enums to support dynamic pipeline orchestration and clear communication between ELS and BOS regarding phase completions.
- **Checkpoints & Sub-tasks:**
    1. **`EssayStatus` Enum Completion:**
        - 🔲 Ensure all `EssayStatus` enum members required for all planned processing stages (Spellcheck, AI Feedback, CJ Assessment, NLP, etc.), including `AWAITING_<STAGE>`, `<STAGE>_IN_PROGRESS`, `<STAGE>_SUCCESS`, `<STAGE>_FAILED`, and `ALL_PROCESSING_COMPLETED`, are present in `common_core/src/common_core/enums.py`.
        - **Validation:** Code review of `enums.py` to confirm completeness.
    2. **Define `ELSBatchPhaseOutcomeV1` Event:**
        - 🔲 Create a new Pydantic event model in `common_core` (e.g., in a new `els_bos_events.py` or an existing relevant file) named `ELSBatchPhaseOutcomeV1` (or similar). This event will be published by ELS to BOS to signal the completion or failure of a specific processing phase for all relevant essays in a batch.
        - 🔲 This event **must** include:
            - `batch_id: str`
            - `phase_name: str` (e.g., "spellcheck", "ai_feedback")
            - `phase_status: str` (e.g., "COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES", "FAILED_CRITICALLY" - consider a new enum for this if distinct from `BatchStatus`)
            - `processed_essays: List[EssayProcessingInputRefV1]` - A list of essays that successfully completed this phase, including their `essay_id` and the **current relevant `text_storage_id`** to be used for the *next* phase.
            - `failed_essay_ids: List[str]` - A list of essay IDs that failed this phase.
            - `correlation_id: Optional[UUID]`
            - Standard event metadata (`event_id`, `timestamp`, `source_service`).
        - **Validation:** Implement contract tests for the `ELSBatchPhaseOutcomeV1` schema, verifying serialization, deserialization, and field constraints.
    3. **`ProcessingEvent` Enum & Topic Mapping:**
        - 🔲 Add a new `ProcessingEvent` enum member for `ELSBatchPhaseOutcomeV1` (e.g., `ELS_BATCH_PHASE_OUTCOME`).
        - 🔲 Ensure `common_core.enums.topic_name()` maps this new `ProcessingEvent` to a dedicated Kafka topic (e.g., `huleedu.els.batch_phase.outcome.v1`).
        - **Validation:** Unit test for `topic_name()` with the new event.
- **Definition of Done for Phase 1:**
  - All required `EssayStatus` enums are finalized in `common_core`.
  - The `ELSBatchPhaseOutcomeV1` event model is defined, documented, and has passing contract tests.
  - `ProcessingEvent` enum and `topic_name()` mapping are updated for the new event.

---

### **Phase 2: ELS Refactoring - Implement `EssayStateMachine` & Update Logic**

- **Goal:** Refactor ELS to use the `transitions` library for managing individual essay states, driven by triggers corresponding to BOS commands and specialized service results. ELS will notify BOS of batch-level phase outcomes.
- **Checkpoints & Sub-tasks:**
    1. **Create `essay_state_machine.py`:**
        - 🔲 Implement the `EssayStateMachine` class in `services/essay_lifecycle_service/essay_state_machine.py` using the `transitions` library as outlined in the provided proposal.
        - 🔲 Define all `EssayStatus` values as states.
        - 🔲 Define all necessary triggers (e.g., `CMD_INITIATE_SPELLCHECK`, `EVT_SPELLCHECK_SUCCEEDED`, `EVT_SPELLCHECK_FAILED`, and equivalents for AI Feedback, CJ Assessment, NLP, etc.). Triggers must be clearly named constants.
        - 🔲 Implement all valid state transitions based on these triggers. The machine defines *possible* transitions; BOS commands will drive the *actual* sequence.
        - **Validation:** Implement comprehensive unit tests for `EssayStateMachine`, covering:
            - Correct initialization to various initial states.
            - Successful execution of all defined valid transitions using trigger methods.
            - Rejection of invalid transitions (attempting to trigger from a state where the trigger is not defined as a source).
            - Correct reporting of `current_status` after transitions.
            - Verification of `can_trigger()` behavior.
    2. **Update `core_logic.py` (`StateTransitionValidator`):**
        - 🔲 Modify `StateTransitionValidator` in `services/essay_lifecycle_service/core_logic.py` to use the `EssayStateMachine` instance for validation, as per the proposal (e.g., `validate_transition` takes the machine and a trigger name).
        - **Validation:** Update existing unit tests for `StateTransitionValidator` to reflect its new reliance on the state machine's `can_trigger()` method.
    3. **Update `state_store.py` (`SQLiteEssayStateStore`):**
        - 🔲 Modify `SQLiteEssayStateStore.update_essay_status_via_machine` (or a similarly named method) to accept the `new_status_from_machine: EssayStatus` and persist it. The Pydantic `EssayState` model continues to store `current_status` as an `EssayStatus` enum.
        - **Validation:** Unit tests for `SQLiteEssayStateStore` methods that interact with essay status verify correct persistence and retrieval, compatible with the state machine's outputs.
    4. **Refactor `batch_command_handlers.py` (or equivalent processing logic):**
        - 🔲 When ELS receives a BOS command (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`):
            - For each relevant essay, retrieve its `EssayState` from the store.
            - Instantiate an `EssayStateMachine` with the essay's `essay_id` and `current_status`.
            - Attempt to fire the corresponding trigger on the state machine (e.g., `essay_machine.trigger(CMD_INITIATE_SPELLCHECK)`).
            - If the transition is successful:
                - Persist the new `essay_machine.current_status` to the `EssayStateStore`.
                - Dispatch the request to the appropriate specialized service (e.g., publish `EssayLifecycleSpellcheckRequestV1`).
            - If the transition fails, log the error and handle appropriately (e.g., notify BOS of an issue with that essay).
        - 🔲 When ELS receives a result event from a specialized service (e.g., `SpellcheckResultDataV1`):
            - Retrieve the essay's `EssayState`.
            - Instantiate an `EssayStateMachine`.
            - Fire the appropriate result trigger (e.g., `EVT_SPELLCHECK_SUCCEEDED` or `EVT_SPELLCHECK_FAILED`).
            - Persist the new state.
            - Check if this essay's completion contributes to a batch-level phase completion (see next sub-task).
        - **Validation:** Unit tests for the message handling logic in ELS, mocking `EssayStateStore`, `EventPublisher`, and `EssayStateMachine`. Tests must verify:
            - Correct instantiation and usage of `EssayStateMachine`.
            - Correct triggers are called based on incoming commands/events.
            - `EssayStateStore` is updated with the new status from the machine.
            - Appropriate events are dispatched to specialized services.
    5. **Implement Batch Phase Outcome Notification to BOS:**
        - 🔲 ELS must track the progress of all essays within a batch for a given commanded phase (e.g., all essays commanded for "spellcheck").
        - 🔲 When all essays in that batch/phase have reached a terminal state for that phase (e.g., all are `SPELLCHECKED_SUCCESS` or `SPELLCHECK_FAILED`), ELS aggregates these outcomes.
        - 🔲 ELS constructs and publishes the new `ELSBatchPhaseOutcomeV1` event to the designated Kafka topic for BOS. This event must contain the list of successfully processed essays and their relevant `text_storage_id`s.
        - **Validation:** Integration tests within ELS (or unit tests with careful mocking) that simulate a series of essay processing results for a batch, verifying that ELS correctly aggregates these and publishes the `ELSBatchPhaseOutcomeV1` event at the appropriate time with the correct payload.
- **Definition of Done for Phase 2:**
  - ELS uses the `EssayStateMachine` for all essay state transitions.
  - ELS correctly processes initiation commands from BOS for various pipeline stages.
  - ELS correctly processes result events from specialized services.
  - ELS reliably publishes the `ELSBatchPhaseOutcomeV1` event to BOS upon completion/failure of a batch-level processing phase, including the necessary list of processed essays and their current storage IDs.
  - All new ELS code is typed, unit-tested (including state machine logic), and documented.

---

### **Phase 3: BOS Enhancements - Dynamic Pipeline Orchestration**

- **Goal:** Enable BOS to define a sequence of processing stages for each batch and orchestrate their execution by commanding ELS based on phase completion events.
- **Checkpoints & Sub-tasks:**
    1. **Store and Manage `ProcessingPipelineState`:**
        - 🔲 When a new batch is registered, BOS (in `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py`) must determine the sequence of pipeline stages for this batch (e.g., `requested_pipelines = ["spellcheck", "cj_assessment", "nlp"]`). This sequence can be based on batch registration parameters, defaults, or other business logic.
        - 🔲 BOS must initialize and persist the `ProcessingPipelineState` Pydantic model (from `common_core.pipeline_models`) for the batch, storing `requested_pipelines` and initializing all stage details (e.g., `spellcheck`, `ai_feedback`, `cj_assessment`, `nlp_metrics`) to a pending status.
        - **Validation:** Unit tests for `batch_processing_service_impl.py` verify that `ProcessingPipelineState` is correctly initialized and stored with the `requested_pipelines` during batch registration.
    2. **Handle `ELSBatchPhaseOutcomeV1` Event:**
        - 🔲 BOS's Kafka consumer (in `services/batch_orchestrator_service/kafka_consumer.py`) must subscribe to and process the new `ELSBatchPhaseOutcomeV1` event from ELS.
        - 🔲 Upon receiving this event:
            - Retrieve the batch's `ProcessingPipelineState` from the `BatchRepositoryProtocol`.
            - Update the status of the `completed_phase_name` within the `ProcessingPipelineState` (e.g., mark "spellcheck" as "COMPLETED_SUCCESSFULLY").
            - Determine the *next* phase from `ProcessingPipelineState.requested_pipelines`.
            - If a next phase exists and has not yet been processed/initiated:
                - Construct the appropriate `BatchService<NextPhaseName>InitiateCommandDataV1` (e.g., `BatchServiceCJAssessmentInitiateCommandDataV1`). This command **must** use the `processed_essays: List[EssayProcessingInputRefV1]` (containing up-to-date `text_storage_id`s) received from the `ELSBatchPhaseOutcomeV1` event as the list of essays to process in the next phase.
                - Publish this command to ELS.
                - Update the `ProcessingPipelineState` to mark this new phase as initiated (e.g., "DISPATCH_INITIATED").
            - If no next phase exists (all stages in `requested_pipelines` are done), update the overall batch status in BOS to reflect final completion.
            - Persist the updated `ProcessingPipelineState`.
        - **Validation:**
            - Unit tests for BOS's Kafka consumer logic, mocking the `BatchRepositoryProtocol` and `BatchEventPublisherProtocol`. These tests must verify:
                - Correct parsing of `ELSBatchPhaseOutcomeV1`.
                - Correct updating of `ProcessingPipelineState`.
                - Correct determination of the next phase based on `requested_pipelines`.
                - Correct construction and publication of the next `BatchService...InitiateCommandDataV1` using the essay list from the ELS event.
                - Correct handling of the end-of-pipeline scenario.
- **Definition of Done for Phase 3:**
  - BOS can define and store a specific sequence of processing stages for each batch.
  - BOS correctly orchestrates the execution of these stages by consuming `ELSBatchPhaseOutcomeV1` events and publishing the appropriate next-stage initiation commands to ELS, using the correct list of essays and their current storage IDs.
  - BOS accurately updates and maintains the `ProcessingPipelineState` for each batch.
  - All new BOS code is typed, unit-tested, and documented.

---

### **Phase 4: End-to-End Validation of Dynamic Pipelines**

- **Goal:** Verify the correct end-to-end operation of dynamically sequenced pipelines orchestrated by BOS and executed via ELS's state machine.
- **Checkpoints & Sub-tasks:**
    1. **Test Scenario Definition & Execution:**
        - 🔲 Define at least two distinct pipeline sequences (e.g., Seq A: Spellcheck -> CJ Assessment; Seq B: Spellcheck -> AI Feedback -> NLP).
        - 🔲 Manually trigger or script the initiation of batches configured with these different pipeline sequences.
        - **Validation:** Observe (via logs, Kafka message tracing, database inspection, and API calls to BOS/ELS/CJ Service for status) that:
            - BOS correctly initiates the first phase for each sequence.
            - ELS transitions essays through the states of the first phase correctly.
            - ELS publishes `ELSBatchPhaseOutcomeV1` correctly upon first phase completion.
            - BOS receives this event and correctly initiates the *second* phase as per the `requested_pipelines` for that batch, using the essay list from ELS's event.
            - This process repeats correctly for all stages in each defined sequence.
            - The `ProcessingPipelineState` in BOS and individual `EssayState`s in ELS accurately reflect the progress through the dynamic pipeline.
            - The `cj_assessment_service` (and other specialized services, mocked if necessary for stages not yet fully integrated) processes requests as expected.
    2. **Handling of Partially Processed Essays (Within a Phase):**
        - 🔲 For a given phase (e.g., AI Feedback), simulate some essays succeeding and some failing.
        - 🔲 Verify that ELS correctly reports this partial success in `ELSBatchPhaseOutcomeV1` (e.g., `phase_status = "COMPLETED_WITH_FAILURES"`, and provides both `processed_essays` and `failed_essay_ids`).
        - 🔲 Verify that BOS, when initiating the *next* phase, only includes the `processed_essays` from the *previous successful* phase in its command to ELS.
        - **Validation:** E2E test scenario demonstrating correct handling and propagation of partially successful phases.
- **Definition of Done for Phase 4:**
  - Successful execution and verification of at least two distinct end-to-end dynamic pipeline sequences.
  - Confirmation that BOS orchestrates the defined sequence correctly based on events from ELS.
  - Confirmation that ELS uses its state machine to correctly manage essay states through multiple, BOS-commanded phases.
  - Confirmation that the list of essays (with correct `text_storage_id`s) is correctly passed from one phase's completion (via ELS event to BOS) to the next phase's initiation (via BOS command to ELS).

---

This detailed task ticket provides a clear, actionable plan with built-in validation steps, addressing your concerns for precision and adherence to architectural principles for a flexible pipeline system.
