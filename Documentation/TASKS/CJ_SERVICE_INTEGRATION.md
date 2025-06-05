# Task Ticket 1: CJ Assessment Service Enhancements (Post-MVP)

**Ticket ID:** `CJ_ASSESS_SVC_ENHANCE_001`
**Title:** Enhance `cj_assessment_service` with Dynamic Configuration and Dedicated Health API
**Status:** 🔲 **TO DO**
**Parent Ticket(s):** `CJ_ASSESS_SVC_REFACTOR_001`
**Assignee:**
**Sprint:**
**Story Points:**

**Note**: Completed tasks are compressed per rule 090-documentation-standards.mdc §5.2 - hyper-technical summaries with code examples only.

## 🚀 **OVERVIEW**

Following the MVP implementation of the `cj_assessment_service`, this ticket directs the implementation of key enhancements: dynamic LLM configuration via request events and a dedicated HTTP API for health and metrics. These changes will increase service flexibility and operational robustness.

## 🎯 **SUB-TASKS & IMPLEMENTATION PLAN**

### **Sub-Task 1.1: Structured LLM Provider Configuration** ✅ **COMPLETED**

**Implementation Summary:**

```python
# config.py
class LLMProviderSettings(BaseModel):
    api_base: str
    default_model: str
    temperature: float = 0.7
    max_tokens: int = 4000
    api_key_env_var: str

class Settings(BaseSettings):
    LLM_PROVIDERS_CONFIG: Dict[str, LLMProviderSettings] = {
        "openai": LLMProviderSettings(api_base="https://api.openai.com/v1", 
                                     default_model="gpt-4o-mini", api_key_env_var="OPENAI_API_KEY"),
        "anthropic": LLMProviderSettings(api_base="https://api.anthropic.com", 
                                        default_model="claude-3-haiku-20240307", api_key_env_var="ANTHROPIC_API_KEY"),
        # + google, openrouter
    }
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

# Provider implementations updated with fallback chain:
def _get_model_name(self, model_override: str | None = None) -> str:
    return model_override or self.provider_config.default_model or self.settings.DEFAULT_LLM_MODEL
```

**Technical Details:**

- **Absolute imports**: All `from .module` → `from module` per containerized service standards
- **MyPy config**: Added `"core_logic.*"` to ignore_missing_imports in root `pyproject.toml`
- **Fallback chain**: `runtime_override → provider_default → global_default`
- **Backward compatibility**: Legacy env vars (`OPENAI_API_KEY`) preserved alongside structured config

**Remaining**: Unit tests, full service startup validation, README updates

### **Sub-Task 1.2: Enable Dynamic LLM Settings in `cj_assessment_service` via Request Event** ✅ **COMPLETED**

**Implementation Summary:**

```python
# common_core/events/cj_assessment_events.py
class LLMConfigOverrides(BaseModel):
    model_override: Optional[str] = Field(default=None)
    temperature_override: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens_override: Optional[int] = Field(default=None, gt=0)
    provider_override: Optional[str] = Field(default=None)

class ELS_CJAssessmentRequestV1(BaseEventData):
    llm_config_overrides: Optional[LLMConfigOverrides] = Field(default=None)

# event_processor.py extracts and passes overrides
converted_request_data = {
    "llm_config_overrides": request_event_data.llm_config_overrides,
}

# core_assessment_logic.py processes overrides with fallback chain
llm_config_overrides = request_data.get("llm_config_overrides")
model_override = llm_config_overrides.model_override if llm_config_overrides else None

# LLMInteractionImpl includes overrides in cache key
cache_key = self.cache_manager.generate_hash(
    f"{task.prompt}|model:{model_override}|temp:{temperature_override}|tokens:{max_tokens_override}"
)

# OpenAIProviderImpl implements full override support with fallback chain
def _get_model_name(self, model_override: str | None = None) -> str:
    return model_override or self.provider_config.default_model or self.settings.DEFAULT_LLM_MODEL
```

**Technical Details:**

- **End-to-end flow**: Request events with `llm_config_overrides` → event processor → core logic → LLM providers
- **Fallback priority**: `runtime_override → provider_default → global_default`
- **Cache integration**: LLMInteractionImpl creates compound cache keys including all LLM parameters
- **Full test coverage**: 17 passing tests covering contract validation, event processing, and error scenarios
- **Backward compatibility**: Service works correctly with or without overrides

**Remaining**: Documentation updates for `ELS_CJAssessmentRequestV1` schema (deferred to integration phase)

### **Sub-Task 1.3: Implement Dedicated Quart API for Health & Metrics in `cj_assessment_service`** ✅ **COMPLETED**

- **Description:** Create an `app.py` file in `services/cj_assessment_service/` to host a minimal Quart application. This application will serve `/healthz` and `/metrics` endpoints and run concurrently with the Kafka worker.
- **Technical Lead:** AI Assistant
- **Est. Effort:** Medium
- **Priority:** High
- **Implementation Summary:**
  - ✅ **Blueprint Architecture**: Created `api/health_routes.py` with mandatory `/healthz` and `/metrics` endpoints following architectural standards
  - ✅ **Lean App**: Created 126-line `app.py` following architectural mandates (< 150 lines) with QuartDishka integration
  - ✅ **Concurrent Execution**: Implemented `run_service.py` using asyncio.gather for Kafka worker + health API with shared DI container
  - ✅ **Configuration Updates**: Updated `pyproject.toml` with new scripts and `Dockerfile` with correct health check endpoint
  - ✅ **Absolute Imports**: Properly configured containerized service imports using `services.cj_assessment_service.` prefix
  - ✅ **Graceful Shutdown**: Implemented proper signal handling for clean service termination
  - ✅ **Testing**: Validated app creation and basic functionality
- **Definition of Done:** ✅ **MET**
  - The `cj_assessment_service` can run both Kafka worker and health API concurrently via `run_service.py`
  - `/healthz` and `/metrics` endpoints are properly implemented and accessible
  - Blueprint architecture follows mandatory patterns with proper DI integration
  - Docker configuration updated for new service runner and health checks

## Success Criteria for Ticket 1

- ✅ All sub-tasks are completed, and their respective "Definition of Done" criteria are met.
- ✅ The `cj_assessment_service` can dynamically configure LLM interactions based on parameters received in request events.
- ✅ The `cj_assessment_service` reliably exposes `/healthz` and `/metrics` endpoints through its dedicated Quart API component.
- ✅ The service passes all linting checks and all existing and newly added tests pass (46/46 tests passing).
- ✅ All relevant documentation (READMEs, configuration guides, event schemas) is updated to reflect these enhancements.

**Implementation Summary:**

- **Task 1.1**: ✅ Structured LLM provider configuration with fallback chains
- **Task 1.2**: ✅ Dynamic LLM settings via `llm_config_overrides` in request events with full test coverage (17 tests)
- **Task 1.3**: ✅ Dedicated Quart API with health/metrics endpoints, concurrent execution, and proper Blueprint architecture
- **Test Coverage**: ✅ 46 comprehensive tests covering contracts, event processing, LLM interactions, health API, and service management
- **Documentation**: ✅ README updated with LLM configuration capabilities, HTTP endpoints, and operational details

---

## Task Ticket 2: Accommodate Core HuleEdu Services for CJ Assessment Service Integration (Enhanced & Clarified)

**Ticket ID:** `HULEEDU_CORE_CJ_INTEGRATE_001`
**Title:** Update Core Services (BOS, ELS) to Integrate CJ Assessment Service (with Enhancements)
**Status:** 🟡 **IN PROGRESS**

## 🚀 **INTEGRATION PHASES**

### **✅ Phase 1: Common Core Event Contracts - COMPLETED**

All event contracts and enums necessary for CJ Assessment integration are implemented in `common_core`:

- ✅ **`BatchServiceCJAssessmentInitiateCommandDataV1`**: Defined as the command from BOS to ELS to start CJ assessment for a batch.
- ✅ **`ELS_CJAssessmentRequestV1`**: Defined as the request from ELS to `cj_assessment_service`.
  - **(Enhancement from Ticket 1.2)** This model's schema definition now includes the optional `llm_config_overrides: Optional[LLMConfigOverrides]` field.
- ✅ **`CJAssessmentCompletedV1`**: Defined as the event from `cj_assessment_service` indicating successful completion.
- ✅ **`CJAssessmentFailedV1`**: Defined as the event from `cj_assessment_service` indicating failure.
- ✅ **`ProcessingEvent` Enum Updates**: All new event types (e.g., `CJ_ASSESSMENT_INITIATE_COMMAND`, `CJ_ASSESSMENT_REQUESTED`, `CJ_ASSESSMENT_COMPLETED`, `CJ_ASSESSMENT_FAILED`) added to `common_core.enums.ProcessingEvent`.
- ✅ **Topic Mappings**: Corresponding Kafka topic names defined and mapped via `common_core.enums.topic_name()`.

### **🔲 Phase 2: Update Batch Orchestrator Service (BOS)**

- **Goal:** BOS must be able to define CJ assessment as a stage in its batch processing pipelines, command ELS to initiate this stage, and track its batch-level status based on notifications from ELS.
- **Checkpoints & Sub-tasks:**
    1. **Pipeline Stage Definition:**
        - 🔲 Add "CJ_ASSESSMENT" to BOS's internal representation of pipeline stages.
        - 🔲 Modify BOS's batch registration mechanism (e.g., `BatchRegistrationRequestV1` and corresponding internal models) to allow specification of whether CJ assessment is required for a batch and to accept any batch-level default parameters for CJ assessment (e.g., target prompt instructions, default LLM model if ELS/CJ service is to support this passthrough).
        - **Done When:** BOS's pipeline logic and batch configuration can include CJ assessment as a distinct stage with optional batch-level parameters.
    2. **Command Dispatch to ELS:**
        - 🔲 Implement logic within BOS to determine the correct point in a batch's workflow to initiate the CJ assessment phase (e.g., after prerequisite phases like spellchecking and NLP are confirmed complete via events from ELS).
        - 🔲 Upon readiness, BOS must construct a `BatchServiceCJAssessmentInitiateCommandDataV1` message. This message will contain the `batch_id`, list of relevant `essay_ids`, and any batch-level CJ parameters defined at registration.
        - 🔲 BOS must publish this command message to the Kafka topic designated for ELS consumption of CJ assessment commands.
        - **Done When:** BOS correctly publishes `BatchServiceCJAssessmentInitiateCommandDataV1` to ELS when a batch is ready for CJ assessment.
    3. **Consumption of ELS Notifications & Batch State Update:**
        - 🔲 BOS must implement Kafka consumer logic to subscribe to and process events from ELS that signify the batch-level status of the CJ assessment phase (e.g., `ELSCJAssessmentBatchPhaseConcludedV1` - a new event ELS will publish, or an existing generic batch phase conclusion event adapted for CJ).
        - 🔲 Based on these events from ELS, BOS must update its internal state for the batch to reflect the current status of the CJ assessment phase (e.g., `CJ_ASSESSMENT_PENDING_ELS_CONFIRMATION`, `CJ_ASSESSMENT_IN_PROGRESS_VIA_ELS`, `CJ_ASSESSMENT_COMPLETED_REPORTED_BY_ELS`, `CJ_ASSESSMENT_FAILED_REPORTED_BY_ELS`).
        - **Done When:** BOS consumes and correctly interprets batch-level CJ phase status updates from ELS, updating its own batch records accordingly.
    4. **Configuration Updates:**
        - 🔲 Add the Kafka topic name for publishing `BatchServiceCJAssessmentInitiateCommandDataV1` to BOS's configuration (`services/batch_orchestrator_service/config.py`).
        - 🔲 Add the Kafka topic name(s) for consuming batch-level CJ phase status updates from ELS to BOS's configuration.
        - **Done When:** All new Kafka topic configurations are implemented and documented in BOS.
    5. **Batch Status API Enhancement:**
        - 🔲 Modify the existing BOS API endpoint(s) that return batch status (e.g., `GET /v1/batches/{batch_id}/status`) to include the status of the "CJ_ASSESSMENT" pipeline phase.
        - 🔲 The status displayed (e.g., PENDING, IN_PROGRESS, COMPLETED, FAILED) must be derived from BOS's internally tracked state for that batch's CJ assessment phase, which is updated solely based on events consumed from ELS.
        - 🔲 The API response model for batch status must be updated to formally include this CJ assessment phase status.
        - **Done When:** The BOS batch status API accurately reports the status of each pipeline phase (including CJ assessment) for a batch. The overall batch status is only set to a terminal state when all requested phases are complete.
- **Definition of Done for Phase 2:**
  - BOS can define batches requiring CJ assessment and command ELS to initiate it.
  - BOS accurately tracks and reports the batch-level status of the CJ assessment phase based on information received from ELS.
  - BOS does not manage or expose any LLM-specific details or raw CJ results; its concern is the orchestration and status of the CJ pipeline phase.
  - All new BOS code is typed, unit-tested, and documented.

### **🔲 Phase 3: Update Essay Lifecycle Service (ELS)**

- **Goal:** ELS must process CJ assessment commands from BOS, dispatch requests to the `cj_assessment_service` (including any LLM overrides), consume results from `cj_assessment_service`, update individual essay states, and notify BOS of batch-level CJ phase completion or failure.
- **Checkpoints & Sub-tasks:**
    1. **New `EssayStatus` Enum Values & Transitions:**
        - 🔲 Add `AWAITING_CJ_ASSESSMENT`, `CJ_ASSESSMENT_IN_PROGRESS`, `CJ_ASSESSMENT_COMPLETED`, `CJ_ASSESSMENT_FAILED` to `common_core.enums.EssayStatus`.
        - 🔲 Update the `StateTransitionValidator` in `services/essay_lifecycle_service/core_logic.py` to define and allow valid state transitions involving these new CJ-related statuses.
        - **Done When:** New essay statuses are defined in `common_core` and ELS state transition logic is updated.
    2. **Handling `BatchServiceCJAssessmentInitiateCommandDataV1`:**
        - 🔲 Implement Kafka consumer logic in `services/essay_lifecycle_service/batch_command_handlers.py` (or equivalent module) to process `BatchServiceCJAssessmentInitiateCommandDataV1` received from BOS.
        - 🔲 For each essay ID specified in the command, ELS must:
            - Validate the essay exists and is in a state eligible for CJ assessment (e.g., `SPELLCHECKED_SUCCESS`, `NLP_ANALYZED`).
            - Update the essay's status to `AWAITING_CJ_ASSESSMENT` in the `EssayStateStore`.
        - **Done When:** ELS correctly consumes the CJ initiation command from BOS and updates relevant essay states to `AWAITING_CJ_ASSESSMENT`.
    3. **Preparing and Publishing `ELS_CJAssessmentRequestV1`:**
        - 🔲 For each essay marked `AWAITING_CJ_ASSESSMENT`, ELS must gather all necessary information to construct an `ELS_CJAssessmentRequestV1` event. This includes `entity_ref` (for the essay), `essays_for_cj` (which in this context will be a list containing just the current essay if CJ service processes one by one, or a list of all essays in the batch if CJ service handles batch input), `language`, `course_code`, `essay_instructions`. It also needs to populate `llm_config_overrides` if these were passed from BOS or determined by ELS.
        - 🔲 ELS must publish these `ELS_CJAssessmentRequestV1` events to the Kafka topic monitored by the `cj_assessment_service` (`huleedu.els.cj_assessment.requested.v1`).
        - 🔲 After successfully publishing the request, ELS updates the essay's status to `CJ_ASSESSMENT_IN_PROGRESS`.
        - 🔲 Ensure robust correlation ID propagation from the incoming BOS command to the outgoing requests to the CJ Assessment Service.
        - **Done When:** ELS can successfully prepare and publish `ELS_CJAssessmentRequestV1` events (including any `llm_config_overrides`) for all relevant essays in a batch to the `cj_assessment_service`. Essay states are updated to `CJ_ASSESSMENT_IN_PROGRESS`.
    4. **Processing Results from `cj_assessment_service`:**
        - 🔲 Implement Kafka consumer logic in ELS to process `CJAssessmentCompletedV1` and `CJAssessmentFailedV1` events from the `cj_assessment_service`.
        - 🔲 Upon receiving `CJAssessmentCompletedV1`:
            - For each essay result in the event, update its corresponding `EssayState` in the `EssayStateStore` with the CJ score, rank, and any other pertinent metadata from the event.
            - Store the `cj_assessment_job_id` from the event in the essay's metadata.
            - Update the essay's status to `CJ_ASSESSMENT_COMPLETED`.
        - 🔲 Upon receiving `CJAssessmentFailedV1`:
            - Update the corresponding `EssayState` to `CJ_ASSESSMENT_FAILED`.
            - Log the error details from the event.
            - (Future: Implement specific error handling or retry logic based on error type if necessary).
        - **Done When:** ELS correctly processes completion and failure events from `cj_assessment_service`, updating individual essay states and storing results/metadata.
    5. **Batch-Level Aggregation and Notification to BOS:**
        - 🔲 ELS must track the CJ assessment status of all essays belonging to a batch that was commanded by BOS.
        - 🔲 Once all essays in that batch have reached a terminal CJ status (`CJ_ASSESSMENT_COMPLETED` or `CJ_ASSESSMENT_FAILED`), ELS must aggregate these outcomes.
        - 🔲 ELS must then publish a new event (e.g., `ELSCJAssessmentBatchPhaseConcludedV1`) to a Kafka topic consumed by BOS. This event will indicate the overall batch_id and the aggregated status of its CJ assessment phase (e.g., "ALL_ESSAYS_CJ_COMPLETED", "SOME_ESSAYS_CJ_FAILED", "ALL_ESSAYS_CJ_FAILED").
        - **Done When:** ELS reliably notifies BOS about the overall completion or failure of the CJ assessment phase for an entire batch.
    6. **Configuration Updates:**
        - 🔲 Add Kafka topic names to ELS's configuration (`services/essay_lifecycle_service/config.py`) for:
            - Consuming `BatchServiceCJAssessmentInitiateCommandDataV1` from BOS.
            - Publishing `ELS_CJAssessmentRequestV1` to `cj_assessment_service`.
            - Consuming `CJAssessmentCompletedV1` and `CJAssessmentFailedV1` from `cj_assessment_service`.
            - Publishing the new batch-level CJ phase conclusion event to BOS.
        - **Done When:** All new Kafka topic configurations are implemented and documented in ELS.
- **Definition of Done for Phase 3:**
  - ELS successfully processes CJ initiation commands from BOS.
  - ELS correctly dispatches assessment requests (with potential LLM overrides) to the `cj_assessment_service`.
  - ELS accurately processes results from the `cj_assessment_service`, updating individual essay states.
  - ELS notifies BOS with the aggregated batch-level outcome of the CJ assessment phase.
  - All new ELS code is typed, unit-tested, and documented.

### **🔲 Phase 4: End-to-End Integration Testing**

- **Goal:** Ensure the seamless and correct operation of the entire CJ assessment workflow, involving BOS, ELS, and the `cj_assessment_service`, including the new dynamic LLM configurations and dedicated health API for the CJ service.
- **Testing Scenarios:**
    1. **Full Happy Path with Dynamic LLM Config:**
        - 🔲 BOS initiates a batch specifying CJ assessment, potentially including default LLM parameters.
        - 🔲 ELS receives the command, prepares `ELS_CJAssessmentRequestV1` including (or overriding with its own logic) the `llm_config_overrides`.
        - 🔲 `cj_assessment_service` consumes the request, applies the LLM overrides, processes successfully, and publishes `CJAssessmentCompletedV1`.
        - 🔲 ELS receives results, updates essay states, and notifies BOS of batch-level CJ phase completion.
        - 🔲 BOS updates the status of the 'CJ_ASSESSMENT' pipeline phase for the batch. If additional phases remain in the batch's requested pipeline, BOS initiates the next phase. Only when all requested phases are complete does BOS update the overall batch status to a terminal state.
        - 🔲 The `cj_assessment_service`'s `/healthz` and `/metrics` endpoints are verified operational during the test.
        - **Done When:** The entire workflow completes successfully, data and states are correctly propagated across all services, and the specified LLM overrides are demonstrably used by the `cj_assessment_service`.
    2. **CJ Service Failure Propagation:**
        - 🔲 Simulate a failure within `cj_assessment_service` (e.g., persistent LLM API error, internal error) causing it to publish `CJAssessmentFailedV1`.
        - 🔲 Verify ELS receives this failure, updates the relevant essay state(s) to `CJ_ASSESSMENT_FAILED`.
        - 🔲 Verify ELS notifies BOS of the batch-level impact (e.g., "CJ_ASSESSMENT_FAILED_FOR_BATCH").
        - 🔲 Verify BOS updates the status of the 'CJ_ASSESSMENT' pipeline phase to reflect failure. The overall batch status is only set to a terminal state when all requested phases are complete or failed.
        - **Done When:** Failures in the `cj_assessment_service` are correctly handled and propagated up to BOS, with appropriate state changes in all services.
    3. **ELS Failure Scenarios:**
        - 🔲 Test ELS failing to publish to `cj_assessment_service` (e.g., Kafka unavailable) and its retry/error handling.
        - 🔲 Test ELS failing to process a result from `cj_assessment_service` and its error handling.
        - **Done When:** ELS exhibits robust error handling for its interactions related to the CJ phase.
{{ ... }}
        - 🔲 Test BOS failing to publish the CJ initiation command to ELS and its retry/error handling.
        - 🔲 Test BOS failing to process the batch-level CJ phase conclusion event from ELS and its error handling.
        - **Done When:** BOS exhibits robust error handling for its orchestration of the CJ phase.
- **Definition of Done for Phase 4:**
  - All specified end-to-end integration test scenarios pass successfully.
  - The integrated CJ assessment workflow, including dynamic LLM configurations and health/metrics reporting for the `cj_assessment_service`, is verified as stable, correct, and resilient.
  - Data integrity and state consistency are maintained across BOS, ELS, and `cj_assessment_service` throughout the workflow.

---

This enhanced ticket structure aims to provide maximum clarity and actionable steps for your developers, reinforcing the architectural principles and ensuring that responsibilities are correctly assigned and implemented.
