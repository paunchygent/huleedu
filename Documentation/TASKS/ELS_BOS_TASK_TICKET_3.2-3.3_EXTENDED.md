# Task: ELS & BOS - Phase 3.2 & 3.3 - Generic Orchestration and Testing Enhancement (Revised Plan)

**Status:** 🟡 In Progress

**Version:** 2.1 (Incorporating Detailed Design Review Feedback)

**Core Goal:** Transition Batch Orchestrator Service (BOS) from hardcoded pipeline phase transitions to a dynamic, map-based orchestration logic. This will allow for flexible pipeline definitions and easier addition of new processing phases, ensuring correct initiation of the first processing phase and robust handling of subsequent phases, guided by type-safety, robust error handling, and clear architectural principles.

---

## Core Principles & Risk Mitigation (Incorporating Review Feedback)

To ensure a robust and maintainable implementation, the following principles and mitigations will be adopted:

1. **Type-Safety for Phase Names (`PhaseName` Enum):**
    * Introduce a `PhaseName(str, Enum)` to define all valid pipeline phases (e.g., `SPELLCHECK`, `AI_FEEDBACK`).
    * This enum will be used as keys in the `phase_initiators_map`, within `ProcessingPipelineState`, and for validating `requested_pipelines` values, eliminating magic strings and providing compile-time safety.

2. **Robust Idempotency & Race Condition Handling:**
    * Wrap `ProcessingPipelineState` updates (e.g., marking a phase as `DISPATCH_INITIATED` or `COMPLETED`) in atomic operations. This can be achieved via compare-and-set logic in repository methods or database-level transactions/constraints (e.g., unique constraint on `(batch_id, phase_name, status_for_uniqueness)` if applicable).
    * Example helper: `async def mark_phase_status_conditionally(repo, batch_id: str, phase: PhaseName, expected_current_status: str, new_status: str) -> bool`.

3. **Centralized and Clear Error Propagation:**
    * Define a specific `InitiationError` exception hierarchy for errors occurring within phase initiators.
    * The core orchestrators (`BatchEssaysReadyHandler`, `DefaultPipelinePhaseCoordinator`) will catch these errors, mark the specific phase as `FAILED` in `ProcessingPipelineState` (recording error details), and publish a diagnostic event (e.g., `PipelinePhaseFailedEvent`).

4. **Lean Initiator Implementations:**
    * Concrete initiator implementations (e.g., `SpellcheckInitiatorImpl`) should be kept lean. Their primary responsibility is to:
        1. Construct the appropriate command data model for the phase.
        2. Publish this command using the `BatchEventPublisherProtocol`.
    * Complex business logic or helper functions should be delegated to `utils/` or shared libraries, not embedded directly within initiators, to keep them focused and maintainable (e.g., adhering to file size/structure guidelines like <400 LoC).

5. **CJ Assessment Initiator Refactoring Strategy:**
    * **Short-term:** Implement a thin adapter class that implements `PipelinePhaseInitiatorProtocol`. This adapter will delegate to the existing `CJAssessmentInitiatorProtocol.initiate_cj_assessment` method, translating parameters as needed. This allows the generic coordinator to work without immediate, deep changes to the CJ initiator's internals.
    * **Long-term (Recommended Early):** Refactor the `CJAssessmentInitiatorProtocol` and its implementation to directly conform to `PipelinePhaseInitiatorProtocol`. This eliminates the adapter and simplifies the overall design. Deferring this too long will accrue complexity.

6. **Handling Hard-coded Ordering Assumptions / Pipeline Validation:**
    * While BOS will execute the `requested_pipelines` list as provided, the definition of a valid and complete pipeline (including prerequisites like spellcheck before AI feedback) is ideally the responsibility of an upstream **Batch Configuration Service (BCS)** (see Future Architectural Considerations).
    * As an interim safeguard if BCS is not yet implemented, BOS could perform basic validation on `requested_pipelines` against known dependencies and fail fast with a clear event if an obviously invalid sequence is provided (e.g., AI Feedback requested without Spellcheck). This is a secondary defense, not primary pipeline definition logic.

## Revised Implementation Plan

### Phase 1: Establish the Generic Initiator Framework

This phase focuses on creating the foundational protocols and the first concrete initiator for BOS-managed processing phases.

1. **Define Core Initiator Protocols & `PhaseName` Enum (`services/batch_orchestrator_service/protocols.py`, `common_core/pipeline_models.py`):**
    * **`PhaseName(str, Enum)`** (in `common_core/pipeline_models.py` or a shared location):
        * Define enum members for all known pipeline phases (e.g., `SPELLCHECK = "spellcheck"`, `AI_FEEDBACK = "ai_feedback"`, `CJ_ASSESSMENT = "cj_assessment"`).
        * This enum is crucial for type-safe dictionary keys and phase identification throughout the system.
    * **`PipelinePhaseInitiatorProtocol`** (in `protocols.py`):
        * Standard method signature:

            ```python
            async def initiate_phase(
                self,
                batch_id: str,
                phase_to_initiate: PhaseName,  # Explicitly use the PhaseName enum
                correlation_id: uuid.UUID | None,
                essays_for_processing: list[EssayProcessingInputRefV1],
                batch_context: BatchRegistrationRequestV1
            ) -> None:
                """Initiate a specific pipeline phase for the batch."""
                ...
            ```

        * Emphasize that `phase_to_initiate` uses the `PhaseName` enum.
    * **`SpellcheckInitiatorProtocol(PipelinePhaseInitiatorProtocol)`** (in `protocols.py`):
        * Inherits, providing specific type hinting if necessary, but primarily for semantic grouping.
    * **CJ Assessment Initiator Refactor:**
        * The `CJAssessmentInitiatorProtocol` and its implementation **must be directly refactored** to conform to `PipelinePhaseInitiatorProtocol` with the standardized `initiate_phase` signature.
        * **No adapter or wrapper should be used.**
        * This ensures a clean, consistent, and maintainable architecture and avoids unnecessary complexity.

2. **Refactor `CJAssessmentInitiatorProtocol` to Implement `PipelinePhaseInitiatorProtocol`:**
    * Refactor both the protocol and its implementation (e.g., `DefaultCJAssessmentInitiator`) to directly implement the new `PipelinePhaseInitiatorProtocol`.
    * Ensure the `initiate_phase` method signature matches the protocol and uses all required parameters (`batch_id`, `phase_to_initiate: PhaseName`, `correlation_id`, `essays_for_processing`, `batch_context`).
    * Remove any legacy or special-case logic that does not fit the generic orchestration model.
    * Update all DI and handler references to use the refactored implementation.
    * Add/adjust tests to cover the new interface and orchestration flow.

3. **Implement `SpellcheckInitiatorImpl` (`services/batch_orchestrator_service/implementations/spellcheck_initiator_impl.py` - New File):**
    * Class `SpellcheckInitiatorImpl` implements `SpellcheckInitiatorProtocol`.
    * **`initiate_phase` method:**
        * Takes `phase_to_initiate: PhaseName` (will be `PhaseName.SPELLCHECK`).
        * Constructs `BatchServiceSpellcheckInitiateCommandDataV1` using `essays_for_processing` and `batch_context` (e.g., for language).
        * Publishes command via injected `BatchEventPublisherProtocol`.
    * **Lean Implementation & Error Handling:**
        * Adhere to the "Lean Initiator" principle: focus on command construction and publishing.
        * Raise `InitiationError` (or specific subclass like `DataValidationError`, `CommandPublishError`) if initiation cannot proceed (e.g., language cannot be determined, critical data missing). This error will be caught by the calling orchestrator.
    * **File Structure:** One `.py` file per concrete initiator (e.g., `spellcheck_initiator_impl.py`).

4. **Update Dependency Injection (`services/batch_orchestrator_service/di.py`):**
    * Provide `SpellcheckInitiatorImpl` and `CJAssessmentInitiatorImpl` (direct implementation, no adapter).
    * **Provide `phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol]`:**
        * This map is central to dynamic dispatch.
        * Keys **must** be `PhaseName` enum members.
        * Example:

            ```python
            from dishka import Provider, Scope, provide
            from common_core.pipeline_models import PhaseName # Assuming PhaseName location
            # ... other imports ...

            class InitiatorMapProvider(Provider):
                @provide(scope=Scope.APP)
                def _provide_phase_initiators_map(
                    self,
                    spellcheck_initiator: SpellcheckInitiatorProtocol,
                    cj_assessment_initiator: CJAssessmentInitiatorProtocol
                ) -> dict[PhaseName, PipelinePhaseInitiatorProtocol]:
                    return {
                        PhaseName.SPELLCHECK: spellcheck_initiator,
                        PhaseName.CJ_ASSESSMENT: cj_assessment_initiator,
                        # Add other phase initiators here as they are implemented
                    }
            ```

    * Ensure this map is injected into `BatchEssaysReadyHandler` and `DefaultPipelinePhaseCoordinator`.

### Phase 2: Refactor `BatchEssaysReadyHandler` to Initiate the *First* Pipeline Phase Generically

This handler is triggered when ELS signals all essay content for a batch is uploaded (`BatchEssaysReady` event).

* **File**: `services/batch_orchestrator_service/implementations/batch_essays_ready_handler.py`
* **Modifications to `handle_batch_essays_ready` (or main message processing method):**
  * **Inject `phase_initiators_map`**.
  * **Dynamic First Phase Determination**:
    * Retrieve `batch_context`.
    * `first_phase_name = batch_context.requested_pipelines[0]` (with error handling).
  * **Generic Idempotency Check**:
    * Use `first_phase_name` and `current_pipeline_state.get_pipeline(first_phase_name)` to check status (e.g., `DISPATCH_INITIATED`, `IN_PROGRESS`, `COMPLETED_SUCCESSFULLY` using `PipelineExecutionStatus` enum).
  * **Retrieve and Use Generic Initiator**:
    * `initiator = self.phase_initiators_map.get(first_phase_name)`
    * If found: `await initiator.initiate_phase(batch_id, correlation_id, essays_to_process, batch_context)`. (`essays_to_process` from `BatchEssaysReady.ready_essays`).
    * Else: Log error, fail phase/batch.
  * **Generic State Update**:
    * Update `ProcessingPipelineState` for `first_phase_name` to `PipelineExecutionStatus.DISPATCH_INITIATED` and set `started_at`.
    * Save updated state.

### Phase 3: Refactor `DefaultPipelinePhaseCoordinator` to Initiate *Subsequent* Pipeline Phases Generically

This coordinator is triggered when any BOS-managed phase completes.

* **File**: `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`
* **Modifications:**
  * **`__init__`**: Inject `phase_initiators_map`. Remove direct `cj_initiator` if refactored.
  * **`_initiate_next_phase` Method**:
    * **Dynamic Next Phase Determination**:
      * Find index of `completed_phase` in `batch_context.requested_pipelines`.
      * Determine `next_phase_name` (e.g., `requested_pipelines[index + 1]`). Handle errors/end of pipeline.
    * **Pre-initiation Checks**:
      * Verify `completed_phase` status is `COMPLETED_SUCCESSFULLY`.
      * Check `next_phase_name` status is `PENDING_DEPENDENCIES`.
    * **Generic Idempotency Check for Next Phase**.
    * **Retrieve and Use Generic Initiator**:
      * `initiator = self.phase_initiators_map.get(next_phase_name)`
      * If found: `await initiator.initiate_phase(batch_id, correlation_id, processed_essays_from_previous_phase, batch_context)`.
      * Else: Log error, fail phase/batch.
    * **Generic State Update**:
      * Update `ProcessingPipelineState` for `next_phase_name` to `DISPATCH_INITIATED` and set `started_at`.
    * **Cleanup**: Remove old hardcoded logic (e.g., `_handle_spellcheck_completion`).

### Phase 4: Implement and Integrate Remaining Phase Initiators

For each BOS-managed processing phase (e.g., `ai_feedback`, `nlp_metrics`, `cj_assessment`):

1. **Define Specific Protocol** (e.g., `AIFeedbackInitiatorProtocol(PipelinePhaseInitiatorProtocol)`).
2. **Create Implementation** (e.g., `AIFeedbackInitiatorImpl`).
3. **Add to `phase_initiators_map`** in `di.py`.
4. Ensure external service sends standardized completion event to BOS, handled by a handler calling `DefaultPipelinePhaseCoordinator.handle_phase_concluded`.

### Phase 5: Comprehensive Testing

* **Unit Tests**:
  * For each new/modified initiator implementation.
  * For `BatchEssaysReadyHandler` (mocking map, repo).
  * For `DefaultPipelinePhaseCoordinator` (mocking map, repo).
  * Cover dynamic phase determination, map lookups, initiator calls, state updates, error handling.
* **Integration Tests**:
  * End-to-end flow: `BatchEssaysReady` -> first phase initiation.
  * Phase completion event -> `DefaultPipelinePhaseCoordinator` -> next phase initiation.
  * Various `requested_pipelines` configurations.
  * Data propagation, idempotency, error scenarios.

### Phase 6: Documentation Update

* Thoroughly update this document (`ELS_BOS_TASK_TICKET_3.2-3.3_EXTENDED.md`) and related architecture documents to reflect:
  * Role of `BatchEssaysReadyHandler` (initiates *first* BOS-managed phase).
  * Role of `DefaultPipelinePhaseCoordinator` (initiates *subsequent* BOS-managed phases).
  * Definition and usage of `PipelinePhaseInitiatorProtocol` and `phase_initiators_map`.
  * Requirement for specific initiator implementations.
  * Updated sequence diagrams and component interactions.

---
**Previous Plan Sections (To be reviewed/removed/archived if superseded by the above):**
*(This section can be used to mark where older plan details were, or they can be removed entirely if this new plan is a full replacement)*
