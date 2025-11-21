# CJ Assessment Service: Architecture & Processing Map

## Overview
This document maps the current state of the CJ Assessment Service, including its internal processing pipeline, state management, and critical integration points with the LLM Provider Service. It serves as the definitive guide for navigating the codebase.

**Reference Foundation**: `docs/operations/cj-assessment-foundation.md`

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
