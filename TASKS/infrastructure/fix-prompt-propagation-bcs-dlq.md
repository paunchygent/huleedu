---
id: fix-prompt-propagation-bcs-dlq
title: Fix Prompt Propagation Bcs Dlq
type: task
status: archived
priority: high
domain: infrastructure
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: ''
owner: ''
program: ''
related: []
labels: []
---

# TASK – Fix Prompt Reference Propagation and BCS DLQ Timeout

## 1. Problem Statement

### 1.1 Prompt Reference Propagation & Prompt Gating

Phase 3.2 introduced **prompt attachment gating** in Batch Conductor Service (BCS). Prompt-dependent pipelines (`cj_assessment`, `ai_feedback`, `nlp`) now require

- `batch_metadata["prompt_attached"] == True`

before BCS will resolve a compatible pipeline. Today, for batches registered via API Gateway:

- `student_prompt_ref` is **defined** on the shared contract `BatchRegistrationRequestV1` and is **consumed** by BOS/ELS/CJ/NLP/RAS.
- API Gateway's `ClientBatchRegistrationRequest` **does not expose** `student_prompt_ref` and `register_batch` never maps it into `BatchRegistrationRequestV1`.
- BOS fallback logic in `ClientPipelineRequestHandler` **relies on** `batch_context.student_prompt_ref` to set `prompt_attached=True` when no `prompt_payload` is provided.
- As a result, prompt-dependent pipelines are rejected by BCS with `BCS_PIPELINE_COMPATIBILITY_FAILED (compatibility_issue="prompt_not_attached")` even when the teacher attached a prompt at registration.

### 1.2 DLQ Publisher Hang Masking Root Cause

BCS uses `KafkaDlqProducerImpl.publish_to_dlq` to log critical failures in pipeline resolution:

- `publish_to_dlq` currently performs `await self.kafka_bus.producer.send(...)` **without a timeout**.
- `DefaultPipelineResolutionService._publish_resolution_failure_to_dlq` awaits `publish_to_dlq(...)` but treats `success=False` as non-fatal.
- When the underlying Kafka `send` hangs, the DLQ path stalls resolution and **masks** the original `BCS_PIPELINE_COMPATIBILITY_FAILED` / `dependency_resolution_failed` error behind an eventual Kafka publish error or global timeout.

This task defines a multi-PR fix plan to:

1. Restore **prompt reference propagation** from API Gateway → BOS → ELS/CJ/NLP/RAS.
2. Make `prompt_attached` behavior and prompt source **observable and testable**.
3. Add a **bounded timeout** to DLQ publishing and (optionally) make it configurable via BCS settings.
4. Lock in behavior with focused **unit and functional tests**.
5. **[PR 5 Addition]** Enable post-registration prompt amendment to support flexible workflow where prompts can be attached during Student Essay Association phase (after registration, before processing).

---

## 2. Goals & Non-Goals

### 2.1 Goals

- **G1 – Correct Prompt Propagation**
  API Gateway must accept and forward `student_prompt_ref` using the shared `StorageReferenceMetadata` shape so that BOS batch context and downstream events carry the prompt reference.

- **G2 – Reliable Prompt Gating**
  For prompt-dependent pipelines, BCS must behave as follows:

  - When prompt is **absent**, surface `BCS_PIPELINE_COMPATIBILITY_FAILED` with `compatibility_issue="prompt_not_attached"` (preserve current error).
  - When prompt is **present** either via `prompt_payload` or persisted `batch_context.student_prompt_ref`, allow resolution and never emit `prompt_not_attached` for that scenario.

- **G3 – Clear BOS Logging for Prompt Source**
  BOS must log whether `prompt_attached` was derived from:

  - `prompt_payload.assignment_id` → `prompt_source="canonical"`
  - `prompt_payload.cms_prompt_ref` → `prompt_source="cms"`
  - `batch_context.student_prompt_ref` → `prompt_source="context"`

- **G4 – DLQ Timeout Safety**
  `KafkaDlqProducerImpl.publish_to_dlq` must not hang indefinitely. A sensible default timeout (5 seconds) should be enforced, with a clean failure path that preserves the original resolution error.

- **G5 – Test & Contract Lock-In**
  Add unit + functional tests to:

  - Assert correct propagation and deserialization of `student_prompt_ref` across relevant services.
  - Assert BCS prompt gating behavior and error codes.
  - Assert DLQ timeout semantics and error logging.

- **G6 – Flexible Prompt Attachment Workflow** **[PR 5]**
  Teachers must be able to attach or replace `student_prompt_ref` on an existing batch after registration but before processing starts, enabling workflows where Content Service uploads occur during Student Essay Association phase.

### 2.2 Non-Goals

- No schema changes to `BatchEssaysRegistered` or ELS/CJ/NLP events (they already understand `student_prompt_ref`).
- No changes to CJ grade-scale logic, anchor infrastructure, or ENG5 runner; only prompt reference wiring and DLQ robustness.
- **[PR 5]** No event emission for prompt amendments (`BatchPromptAttached` etc.).

---

## 3. PR Breakdown

### PR 1 – API Gateway Prompt Reference Contract (P0)

**Objective:** Expose `student_prompt_ref` on API Gateway's registration model and forward it into BOS using strongly-typed `StorageReferenceMetadata`.

**Primary Files:**

- `services/api_gateway_service/routers/batch_routes.py`
- `libs/common_core/src/common_core/api_models/batch_registration.py` (contract reference only; no change expected)
- `libs/common_core/src/common_core/metadata_models.py` (`StorageReferenceMetadata` definition; contract reference only)

**Planned Changes:**

1. **Client Model Type**
   Update `ClientBatchRegistrationRequest`:

   - Add field: `student_prompt_ref: StorageReferenceMetadata | None = None`
   - Use the shared type directly so that OpenAPI and validation leverage the existing `StorageReferenceMetadata` schema.

2. **Mapping to BOS Contract**
   In `register_batch` when building `BatchRegistrationRequestV1`:

   - Populate `student_prompt_ref=registration_request.student_prompt_ref` (types now align).
   - Preserve all existing identity threading (`user_id`, `org_id`) and CJ defaults.

3. **HTTP Schema Alignment**
   - Validate that the generated OpenAPI schema for `/batches/register` shows `student_prompt_ref` with the same structure as `PipelinePromptPayload.cms_prompt_ref`.

**Tests:**

- **New unit test** for `ClientBatchRegistrationRequest` serialization/deserialization:

  - Location: `services/api_gateway_service/tests/test_batch_routes_registration.py` (new) or extend existing registration tests.
  - Scenario: send JSON including a `student_prompt_ref` with `ContentType.STUDENT_PROMPT_TEXT` reference and assert that:
    - Pydantic constructs `StorageReferenceMetadata` correctly.
    - `internal_model.student_prompt_ref` equals the provided reference.

---

### PR 2 – BOS Prompt Metadata & Logging (P0)

**Objective:** Ensure BOS sets `prompt_attached` correctly, updates `batch_context.student_prompt_ref` when a `cms_prompt_ref` is provided, and logs the prompt source clearly.

**Primary Files:**

- `services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py`
- `services/batch_orchestrator_service/implementations/batch_context_operations.py`
- `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py` (verifying event propagation)
- Tests: `services/batch_orchestrator_service/tests/test_client_pipeline_request_handler.py`

**Planned Changes:**

1. **Prompt Source Logging**
   In `ClientPipelineRequestHandler.handle_client_pipeline_request`:

   - After computing `prompt_attached`, `prompt_source`, and `assignment_context`, add a **single structured log line** that includes:
     - `batch_id`, `requested_pipeline`, `correlation_id`
     - `prompt_attached`, `prompt_source`, `assignment_id`
   - Ensure log is emitted before calling `bcs_client.resolve_pipeline`.

2. **Prompt Context Fallback**
   - Preserve existing logic:
     - Use `prompt_payload` when present (canonical or CMS).
     - When `prompt_payload` is `None` and `getattr(batch_context, "student_prompt_ref", None)` is truthy, set `prompt_attached=True` and `prompt_source="context"`.
   - Confirm `batch_context` is a `BatchRegistrationRequestV1` instance with `student_prompt_ref: StorageReferenceMetadata | None` populated by PR 1.

3. **BOS → ELS/CJ/NLP Prompt Reference Flow (No Code Change, Documented Here)**

   - BOS persists `BatchRegistrationRequestV1` via `BatchContextOperations.store_batch_context` with `processing_metadata=registration_data.model_dump()`.
   - BOS emits `BatchEssaysRegistered` with `student_prompt_ref=registration_data.student_prompt_ref`.
   - ELS/CJ/NLP/Result Aggregator already consume `student_prompt_ref` via `StorageReferenceMetadata`.

4. **Persist CMS Prompt Ref** **[Enhancement from PR 5 context]**
   When `prompt_payload.cms_prompt_ref` is present:

   - Update `batch_context.student_prompt_ref = prompt_payload.cms_prompt_ref` (currently done in-memory at line 208).
   - **Persist** the updated context via `BatchContextOperations.store_batch_context()`.
   - This ensures subsequent pipeline requests (without `prompt_payload`) can rely on `prompt_source="context"`.

**Tests:**

- **Unit test** for `ClientPipelineRequestHandler`:

  - Location: extend `services/batch_orchestrator_service/tests/test_client_pipeline_request_handler.py`.
  - Scenarios:
    - **S1 – Prompt from payload**: `prompt_payload.assignment_id` set; verify `batch_metadata["prompt_attached"] is True`, `prompt_source="canonical"`, and that logging includes these fields.
    - **S2 – Prompt from CMS**: `prompt_payload.cms_prompt_ref` set; verify `prompt_source="cms"` and `batch_context.student_prompt_ref` updated **and persisted**.
    - **S3 – Prompt from context**: `prompt_payload=None`, `batch_context.student_prompt_ref` set; verify `prompt_source="context"`, `prompt_attached=True`.

---

### PR 3 – BCS Prompt Gating & Error Semantics (P0)

**Objective:** Lock in the prompt-gating semantics at BCS level and assert the correct error code + compatibility issue when prompts are missing.

**Primary Files:**

- `services/batch_conductor_service/implementations/pipeline_rules_impl.py`
- `services/batch_conductor_service/api_models.py`
- Tests: `services/batch_conductor_service/tests/test_pipeline_rules_impl.py` (new) and/or extend `test_pipeline_resolution_service.py`.

**Planned Changes:**

1. **Behavior (Already Implemented, Test Only)**

   - `DefaultPipelineRules.validate_pipeline_compatibility`:
     - Recognizes prompt-dependent phases: `AI_FEEDBACK`, `CJ_ASSESSMENT`, `NLP`.
     - Requires `batch_metadata and batch_metadata.get("prompt_attached")` to be truthy.
     - When condition fails, increments `prompt_prerequisite_blocked_total` and calls `raise_pipeline_compatibility_failed(...)` with `compatibility_issue="prompt_not_attached"`.

2. **Tests for Missing Prompt (Broken Case, Explicitly Preserved)**

   - Add a unit test that calls `validate_pipeline_compatibility` with `batch_metadata={"prompt_attached": False}` and asserts:
     - A `HuleEduError` is raised.
     - `error_detail.error_code == ErrorCode.BCS_PIPELINE_COMPATIBILITY_FAILED`.
     - `error_detail.details["compatibility_issue"] == "prompt_not_attached"`.

3. **Functional Test for Fixed Case (Prompt Present)**

   - Update functional test: `tests/functional/test_e2e_identity_threading.py`.
   - For a scenario where a batch is registered **with** a valid `student_prompt_ref`:
     - Request CJ pipeline **without** `prompt_payload`.
     - Assert pipeline execution succeeds end-to-end and no `BCS_PIPELINE_COMPATIBILITY_FAILED` with `prompt_not_attached` appears in logs.

---

### PR 4 – DLQ Timeout & Settings (P1)

**Objective:** Prevent DLQ publishing from hanging indefinitely, and make timeout configurable for long-term stability.

**Primary Files:**

- `services/batch_conductor_service/implementations/kafka_dlq_producer_impl.py`
- `services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py`
- `services/batch_conductor_service/config.py` (or equivalent settings module)
- Tests: `services/batch_conductor_service/tests/test_dlq_producer.py`, `services/batch_conductor_service/tests/test_pipeline_resolution_service.py`

**Planned Changes:**

1. **Configurable Timeout Setting**
   In BCS settings (e.g. `Settings` in `config.py`):

   - Add: `DLQ_PUBLISH_TIMEOUT_SECONDS: float = 5.0`
   - Wire this value into `KafkaDlqProducerImpl` via DI (constructor parameter or direct settings injection).

2. **Timeout Logic in DLQ Producer**

   - Import `asyncio` and wrap the producer send call:
     - `await asyncio.wait_for(self.kafka_bus.producer.send(...), timeout=self._timeout_seconds)`.
   - On `asyncio.TimeoutError`:
     - Log `"DLQ publish timeout"` with `base_topic`, `dlq_topic`, `dlq_reason`, and `original_event_id`.
     - Return `False`.

3. **Preserve Primary Error Semantics**

   - `DefaultPipelineResolutionService._publish_resolution_failure_to_dlq` already:
     - Inspects `success` and logs when `not success` but does **not** override the main error.
   - No semantic change needed; ensure tests confirm:
     - DLQ timeout does **not** alter the raised `HuleEduError` in `resolve_pipeline()` / `resolve_pipeline_request()`.

**Tests:**

- Extend `test_dlq_producer.py` with a case where `producer.send` never completes or raises `asyncio.TimeoutError`:
  - Assert `publish_to_dlq()` returns `False` and does not raise.
  - Assert timeout log entry contains `dlq_topic` and `original_event_id`.

- Extend `test_pipeline_resolution_service.py`:
  - Simulate DLQ timeout by having `dlq_producer.publish_to_dlq` return `False` or raise/reject internally.
  - Assert:
    - `resolve_pipeline()` still raises the expected `HuleEduError` for the underlying problem.
    - DLQ failure is only visible via logs/metrics.

---

### PR 5 – Batch Prompt Amendment Endpoint (P1)

**Objective:** Enable teachers to attach or replace `student_prompt_ref` on an existing batch after registration but before processing starts, supporting workflows where prompts are uploaded to Content Service during Student Essay Association phase.

**Required Reading:**

Before implementing PR 5, the coding assistant **must** read and understand:

1. **PR Context**: This task file sections for PR 1–4 (above) to understand the overall prompt propagation architecture.
2. **Test Creation Standards**: `.claude/rules/075-test-creation-methodology.md` and `.claude/rules/075.1-parallel-test-creation-methodology.md`.
3. **Service Architecture Rules**:
   - `.claude/rules/020-architectural-mandates.md` (DDD, service boundaries, explicit contracts)
   - `.claude/rules/020.3-batch-orchestrator-service-architecture.md` (BOS ownership of batch context)
   - `.claude/rules/020.10-api-gateway-service.md` (proxy patterns, JWT auth, identity injection)
4. **Research Context**: The research-diagnostic agent investigation documented CJ Assessment Service's prompt attachment pattern (`services/cj_assessment_service/api/admin/student_prompts.py`) and confirmed BOS ownership of batch context via `BatchContextOperations`.

**Primary Files:**

- `libs/common_core/src/common_core/api_models/batch_prompt_amendment.py` (new shared contract)
- `services/batch_orchestrator_service/api/batch_routes.py` (new PATCH endpoint)
- `services/api_gateway_service/routers/batch_routes.py` (proxy endpoint)
- Tests:
  - `services/batch_orchestrator_service/tests/test_batch_prompt_amendment.py` (new)
  - `services/api_gateway_service/tests/test_batch_routes_amendment.py` (new)
  - `tests/integration/test_batch_prompt_amendment_e2e.py` (new)

**Planned Changes:**

1. **Shared Contract Model**
   Create `libs/common_core/src/common_core/api_models/batch_prompt_amendment.py`:

   ```python
   class BatchPromptAmendmentRequest(BaseModel):
       """Request to attach/replace student prompt reference on an existing batch."""
       student_prompt_ref: StorageReferenceMetadata = Field(
           description="Content Service reference for the student prompt"
       )
   ```

   This model is used by both BOS internal endpoint and API Gateway router.

2. **BOS Internal Endpoint**
   In `services/batch_orchestrator_service/api/batch_routes.py`, add:

   - **Route**: `PATCH /v1/batches/{batch_id}/prompt`
   - **Authentication**: Extract `X-User-ID` and (optionally) `X-Org-ID` from headers (set by API Gateway). If `X-User-ID` is missing → **401** with error code `auth_required`.
   - **Request Parsing**: Parse body as `BatchPromptAmendmentRequest`. Pydantic validation errors → **400/422** with error code `invalid_request`.
   - **Load Existing Context**: Use `BatchContextOperations.get_batch_context(batch_id)`. If `None` → **404** with error code `batch_not_found`.
   - **Ownership Validation**: Compare `batch_context.user_id` with `X-User-ID`. If mismatch → **403** with error code `batch_not_owned_by_user`.
   - **Lifecycle/State Check**: Load batch state from batch repository. Only allow amendment while batch is in pre-processing states:
     - **Allowed**: `REGISTERED`, `ASSOCIATION_PENDING`, `ASSOCIATION_CONFIRMED`
     - **Forbidden**: `PROCESSING_STARTED`, `COMPLETED`, `FAILED`
     - If forbidden → **409** with error code `batch_not_editable_for_prompt_amendment`.
   - **Content Service Validation**:
     - Extract `storage_id` and/or `path` from `student_prompt_ref.references[ContentType.STUDENT_PROMPT_TEXT]`.
     - Make async GET call to Content Service to verify the object exists.
     - If object is missing or returns non-2xx status → **400** with error code `invalid_student_prompt_ref`.
   - **Update Context**: Set `batch_context.student_prompt_ref = amendment_request.student_prompt_ref` (allow overwrite, idempotent "last write wins").
   - **Persist**: Call `BatchContextOperations.store_batch_context(batch_id, registration_data=batch_context, correlation_id=...)` to update the `processing_metadata` JSONB for this batch (UPDATE existing row, not INSERT new).
   - **Logging**: Emit structured log with fields: `batch_id`, `user_id`, `correlation_id`, `operation="batch_prompt_amended"`.
   - **Response**: Return **200 OK** with JSON:

     ```json
     {
       "status": "success",
       "batch_id": "<batch_id>",
       "student_prompt_ref": { ...StorageReferenceMetadata... }
     }
     ```

   **Error Codes Summary**:
   - `401` – `auth_required` (no X-User-ID header)
   - `400` – `invalid_student_prompt_ref` (Content Service validation failed) or `invalid_request` (Pydantic validation errors)
   - `403` – `batch_not_owned_by_user` (ownership mismatch)
   - `404` – `batch_not_found` (batch does not exist)
   - `409` – `batch_not_editable_for_prompt_amendment` (batch in non-editable state)

3. **API Gateway Proxy Endpoint**
   In `services/api_gateway_service/routers/batch_routes.py`, add:

   - **Route**: `PATCH /v1/batches/{batch_id}/prompt`
   - **Request Validation**: Validate request body as `BatchPromptAmendmentRequest` (same shared model). **If validation fails** at gateway, return **400/422** directly and **do not call BOS**.
   - **JWT Extraction**: Extract `user_id` and `org_id` from JWT (existing DI pattern).
   - **Build BOS URL**: `f"{settings.BOS_URL}/v1/batches/{batch_id}/prompt"`
   - **Forward Request**: PATCH with:
     - Body: `json=prompt_request.model_dump(mode="json")`
     - Headers: `X-User-ID`, `X-Org-ID` (if used), `X-Correlation-ID`
     - Timeout: 10 seconds (same as other BOS calls)
   - **Pass Through Response**: Return BOS status code and JSON body transparently to client.
   - Follow the same logging and error-pass-through patterns as existing `/batches/register` proxy.

4. **Integration with PR 2 Enhancement** (Optional but Recommended)
   The PR 2 enhancement to persist `cms_prompt_ref` from pipeline requests complements PR 5 by ensuring late-binding prompts are not "lost" for future pipelines. Both PRs can be developed in parallel or PR 5 can be implemented after PR 2 is stable.

**Tests:**

- **BOS Unit Tests** (`services/batch_orchestrator_service/tests/test_batch_prompt_amendment.py`):

  1. `test_amend_batch_prompt_success`:
     - Existing batch in `ASSOCIATION_CONFIRMED` state, correct owner, valid `storage_id` from Content Service.
     - Assert:
       - Updated context has `student_prompt_ref` set to amendment value.
       - `store_batch_context()` is called.
       - Response is 200 OK with correct JSON shape.

  2. `test_amend_batch_prompt_not_found`:
     - Batch does not exist.
     - Assert: 404 with error code `batch_not_found`.

  3. `test_amend_batch_prompt_ownership_mismatch`:
     - `X-User-ID` does not match `batch_context.user_id`.
     - Assert: 403 with error code `batch_not_owned_by_user`.

  4. `test_amend_batch_prompt_not_editable`:
     - Batch state is `PROCESSING_STARTED`.
     - Assert: 409 with error code `batch_not_editable_for_prompt_amendment`.

  5. `test_amend_batch_prompt_invalid_storage_ref`:
     - Content Service validation fails (404 or non-2xx).
     - Assert: 400 with error code `invalid_student_prompt_ref`.

  6. `test_amend_batch_prompt_overwrite`:
     - Two consecutive PATCH calls with different `student_prompt_ref` values.
     - Assert: Second value wins (idempotent "last write wins").

- **API Gateway Unit Tests** (`services/api_gateway_service/tests/test_batch_routes_amendment.py`):

  1. `test_proxy_batch_prompt_amendment_success`:
     - Successful proxy path with JWT → `X-User-ID` propagation.
     - Assert: BOS endpoint called with correct headers and body.

  2. `test_proxy_batch_prompt_amendment_validation_error`:
     - Malformed request body (invalid `StorageReferenceMetadata`).
     - Assert: 400/422 returned directly by gateway, BOS is **not called**.

  3. `test_proxy_batch_prompt_amendment_error_passthrough`:
     - BOS returns 404/403/409/400.
     - Assert: Status code and JSON body passed through transparently.

- **Integration/E2E Test** (`tests/integration/test_batch_prompt_amendment_e2e.py`):

  **Scenario**:
  1. Register batch via API Gateway **without** `student_prompt_ref`.
  2. Upload essays, batch transitions to `ASSOCIATION_CONFIRMED` state.
  3. PATCH `/v1/batches/{batch_id}/prompt` via API Gateway with valid `StorageReferenceMetadata` (referencing a prompt uploaded to Content Service).
  4. Request CJ pipeline via API Gateway **without** `prompt_payload`.
  5. **Assert**:
     - BOS logs show `prompt_source="context"`, `prompt_attached=True`.
     - BCS does **not** raise `BCS_PIPELINE_COMPATIBILITY_FAILED` with `compatibility_issue="prompt_not_attached"`.
     - Pipeline resolves and starts successfully (or reaches expected state if full processing is out of scope).

**Sequencing Recommendation:**

- **Option A (Parallel)**: Develop PR 5 alongside PR 1–4. Provides full prompt flexibility immediately but requires coordinating more changes.
- **Option B (Sequential)**: Implement PR 5 after PR 1–3 are stable. Recommended approach as it builds on proven prompt propagation foundation.

**Effort Estimate:**

- BOS endpoint implementation: 3–4 hours
- API Gateway proxy: 1–2 hours
- Content Service validation helper: 1 hour
- Unit tests (BOS + API Gateway): 3–4 hours
- Integration test: 2–3 hours
- **Total**: 10–14 hours

---

## 4. Verification Checklist

1. **Unit Tests**

   - `pdm run pytest-root services/api_gateway_service/tests`
   - `pdm run pytest-root services/batch_orchestrator_service/tests/test_client_pipeline_request_handler.py`
   - `pdm run pytest-root services/batch_conductor_service/tests/test_dlq_producer.py`
   - `pdm run pytest-root services/batch_conductor_service/tests/test_pipeline_resolution_service.py`
   - **[PR 5]** `pdm run pytest-root services/batch_orchestrator_service/tests/test_batch_prompt_amendment.py`
   - **[PR 5]** `pdm run pytest-root services/api_gateway_service/tests/test_batch_routes_amendment.py`

2. **Functional Tests**

   - `pdm run pytest-root tests/functional/test_e2e_identity_threading.py -v`
   - Confirm logs show:
     - For the **broken** case (no prompt on registration):
       - `BCS_PIPELINE_COMPATIBILITY_FAILED` with `compatibility_issue="prompt_not_attached"`.
     - For the **fixed** case (prompt attached at registration):
       - No `prompt_not_attached` error for CJ/NLP/AI feedback pipelines.
   - **[PR 5]** `pdm run pytest-root tests/integration/test_batch_prompt_amendment_e2e.py -v`

3. **Observability Checks**

   - BOS logs include clear `prompt_attached`, `prompt_source`, `assignment_id` fields per pipeline request.
   - BCS metrics: `prompt_prerequisite_blocked_total{pipeline_name="cj_assessment"}` increments only when prompt is truly missing.
   - DLQ logs show `DLQ publish timeout` events in failure scenarios, with no impact on the primary error surfacing to BOS.
   - **[PR 5]** BOS logs include `operation="batch_prompt_amended"` entries with `batch_id`, `user_id`, `correlation_id`.

4. **Quality Gates**

- `pdm run typecheck-all`
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`

All must be green after each PR.

---

## 5. Risks & Rollback

- **Risk:** Mis-typed `student_prompt_ref` in API Gateway request payloads.
  **Mitigation:** Rely on `StorageReferenceMetadata` validation; surface as clear HTTP 4xx errors.

- **Risk:** DLQ timeout too aggressive under heavy Kafka load.
  **Mitigation:** Configurable `DLQ_PUBLISH_TIMEOUT_SECONDS` with safe default; log-based tuning.

- **Risk:** Prompt gating regression in BCS.
  **Mitigation:** Unit tests for `validate_pipeline_compatibility`; functional tests asserting presence/absence of `prompt_not_attached` errors.

- **[PR 5] Risk:** Prompt amendment attempted on batches in invalid states (already processing/completed).
  **Mitigation:** Lifecycle state validation in BOS endpoint; clear 409 error code with descriptive message.

- **[PR 5] Risk:** Content Service validation adds latency to amendment requests.
  **Mitigation:** Use reasonable timeout for Content Service GET calls (e.g., 5 seconds); fail fast with clear error.

Rollback is straightforward per PR: revert individual PRs in reverse order (PR 5 → PR 4 → PR 3 → PR 2 → PR 1) if regressions are observed.
