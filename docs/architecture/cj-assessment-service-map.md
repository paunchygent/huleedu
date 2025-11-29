# CJ Assessment Service: Architecture & Processing Map

## Overview
This document maps the current state of the CJ Assessment Service, including its internal processing pipeline, state management, and critical integration points with the LLM Provider Service. It serves as the definitive guide for navigating the codebase.

**Reference Foundation**: `docs/operations/cj-assessment-runbook.md`

---

## Completion & Stability Semantics

The callback-driven workflow applies three distinct gates before a batch is
considered ready for completion:

- **Callback gate** (per-iteration): `check_workflow_continuation` only returns
  `True` when `submitted_comparisons > 0` and
  `submitted_comparisons == completed_comparisons + failed_comparisons`.
- **Stability gate** (score deltas): `trigger_existing_workflow_continuation`
  recomputes Bradley–Terry scores using all successful comparisons in the
  database and compares them to the previously persisted `bt_scores`.
  Stability is considered passed only when:
  - `callbacks_received >= MIN_COMPARISONS_FOR_STABILITY_CHECK`, and
  - `max_score_change <= SCORE_STABILITY_THRESHOLD`.
- **Success‑rate gate** (PR‑2): a per‑batch success‑rate is computed as
  `completed_comparisons / callbacks_received` (when callbacks have arrived).
  If `MIN_SUCCESS_RATE_THRESHOLD` is defined and numeric, the stability
  condition additionally requires `success_rate >= MIN_SUCCESS_RATE_THRESHOLD`.

When an iteration completes, `trigger_existing_workflow_continuation` decides
between three paths:

- **Finalize successfully** when stability has passed, or when the callback
  count has reached the batch’s `completion_denominator()` (which is derived
  from `min(total_budget, nC2)`), or when the global comparison budget is
  exhausted.
- **Finalize as failure** when caps/budgets are hit but the success‑rate gate
  fails (zero successes, or a success‑rate below `MIN_SUCCESS_RATE_THRESHOLD`).
  In this case `BatchFinalizer.finalize_failure` marks the upload as
  `ERROR_PROCESSING`, transitions `CJBatchState` to `FAILED`, and emits a
  `CJAssessmentFailedV1` thin event to ELS so that downstream batch/essay
  state reflects a hard failure instead of hanging.
- **Request additional comparisons** when callbacks for the current iteration
  are complete, stability has not passed, and comparison budget remains.

`MAX_PAIRWISE_COMPARISONS` and the per‑batch `completion_denominator()` work
in tandem:

- `MAX_PAIRWISE_COMPARISONS` is a global hard cap on how many comparisons CJ
  will attempt for a batch (subject to per‑request overrides).
- `completion_denominator()` computes the effective denominator used for
  completion math as `min(total_budget, nC2)` where `nC2` is derived from the
  batch’s expected essay count. Small nets therefore finalize once their
  small n‑choose‑2 graph is saturated, while large nets are naturally capped
  by budget.

---

## 1. Core Processing Pipeline
The service operates on an asynchronous, callback-driven event loop.

### A. Request Ingestion (Start)
**Trigger**: Kafka Event `ELS_CJAssessmentRequestV1` from Batch Orchestrator Service.

1. **Event Processor Entry**
    * **File**: `services/cj_assessment_service/event_processor.py`
    * **Function**: `process_single_message` -> `handle_cj_assessment_request`
    * **Responsibility**: Deserializes envelope, sets up OpenTelemetry trace context.

2. **Request Handling & Hydration**
    * **File**: `services/cj_assessment_service/message_handlers/cj_request_handler.py`
    * **Action**:
        * Hydrates prompt/rubric text via `ContentClientProtocol`.
        * Transforms event into internal `CJAssessmentRequest`.
        * Calls `workflow_orchestrator.run_cj_assessment_workflow`.

3. **Workflow Initiation**
    * **File**: `services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py`
    * **Logic**:
        * Creates initial `CJBatchState` (State: `WAITING_CALLBACKS`).
        * Generates all possible pairwise comparisons (nC2).
        * Submits initial "wave" of comparisons to LLM Provider (capped by budget/batch size).

### B. The Async Callback Loop (Core)
**Trigger**: Kafka Event `LLMComparisonResultV1` (on topic `llm.provider.callback.v1`) from LLM Provider.

1. **Callback Ingestion**
    * **File**: `services/cj_assessment_service/message_handlers/llm_callback_handler.py`
    * **Function**: `handle_llm_comparison_callback`
    * **Logic**: Idempotency check -> Delegates to `batch_callback_handler.py`.

2. **State Update (Atomic)**
    * **File**: `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
    * **Action**:
        * Updates specific comparison record with result (A won/B won).
        * **Success**: Increments `batch_state.completed_comparisons`.
        * **Error**: Increments `batch_state.failed_comparisons` (Atomic update).
        * **Retry**: If error is transient (5xx/Network), adds to `failed_pool` for `BatchRetryProcessor`.

3. **Continuation Decision**
    * **File**: `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
    * **Trigger**: Occurs after *every* callback.
    * **Check**: `callbacks_received == submitted_comparisons` (Is the current wave done?).
    * **Decision Logic**:
        * **CONTINUE**: If (Stability < Threshold) AND (Budget Remaining) -> `batch_submitter.submit_comparison_batch`.
        * **FINALIZE**: If (Stability Reached) OR (Budget Exhausted) OR (Hard Cap Reached) -> `finalize_scoring`.

### C. Finalization & Output
**Trigger**: `workflow_continuation.py` decides to finalize.

1. **Scoring & Ranking**
    * **File**: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py`
    * **Algorithm**: Bradley-Terry Model.
    * **Action**:
        * Transitions state to `SCORING`.
        * Computes scores using all completed comparisons.
        * Generates `AssessmentResultV1` (Rankings) and `GradeProjection` (if assignment exists).

2. **Dual Event Publication**
    * **File**: `services/cj_assessment_service/cj_core_logic/dual_event_publisher.py`
    * **Outputs**:
        1. **Thin Event** (`huleedu.assessment.completed.v1`): To BOS (State advancement).
        2. **Rich Event** (`huleedu.assessment.results.v1`): To RAS (Analytics/UI).

3. **Terminal State**
    * **Final State**: `COMPLETED`.

---

## 2. Integration Mechanics: CJ <-> LLM Provider

This interaction is strictly asynchronous to handle long-running LLM inference (10-60s).

### Outbound: CJ -> LLM Provider (HTTP)
**Protocol**: HTTP POST (Fire-and-Forget pattern).

* **Client**: `services/cj_assessment_service/implementations/llm_provider_service_client.py`
* **Mechanism**:
    * Sends POST to LLM Provider `/api/v1/llm/compare`.
    * **Expects HTTP 202 Accepted**.
    * **Critical**: Does *not* wait for inference. The HTTP connection closes immediately after queuing.
* **Provider Side**:
    * **Entry**: `services/llm_provider_service/api/llm_routes.py`.
    * **Queue**: Request is validated and pushed to internal `QueueProcessor`.

### Inbound: LLM Provider -> CJ (Kafka)
**Protocol**: Kafka Message (Callback).

* **Provider Side**:
    * **Component**: `services/llm_provider_service/implementations/queue_processor_impl.py`.
    * **Action**: Upon inference completion, publishes `LLMComparisonResultV1` to `llm.provider.callback.v1`.
* **CJ Side**:
    * **Listener**: `services/cj_assessment_service/kafka_consumer.py`.
    * **Routing**: `_process_llm_callback_idempotent` -> `handle_llm_comparison_callback`.

---

## 3. Auxiliary Flows

### Admin Anchor Registration
**Purpose**: Register calibrated essays ("Anchors") into the system.

* **Endpoint**: `POST /api/v1/anchors/register` (`api/anchor_management.py`).
* **Flow**:
    1. Validates grade against Assignment's `GradeScale`.
    2. Stores essay text in **Content Service** (via `ContentClient`).
    3. Registers metadata in CJ Database with `storage_id` reference.

---

## 4. State Definitions

| State Enum | Context | Description |
| :--- | :--- | :--- |
| `WAITING_CALLBACKS` | CJBatchState | Active state. Listening for callbacks. Auto-triggers continuation checks. |
| `SCORING` | CJBatchState | Transient state. Locked while computing Bradley-Terry scores. |
| `COMPLETE_STABLE` | CJBatchStatus | Internal status indicating scoring converged successfully. |
| `COMPLETED` | CJBatchState | Terminal state. Events published. Ready for archiving. |
| `FAILED_CRITICALLY` | CJBatchStatus | Manual intervention required. |

## 5. Key File Map

| Component | Primary File |
| :--- | :--- |
| **Orchestrator** | `cj_core_logic/workflow_orchestrator.py` |
| **Continuation Logic** | `cj_core_logic/workflow_continuation.py` |
| **Callback Handler** | `cj_core_logic/batch_callback_handler.py` |
| **State Manager** | `cj_core_logic/callback_state_manager.py` |
| **Finalizer** | `cj_core_logic/batch_finalizer.py` |
| **Retry Processor** | `cj_core_logic/batch_retry_processor.py` |
| **Kafka Consumer** | `kafka_consumer.py` |
| **LLM Client** | `implementations/llm_provider_service_client.py` |
