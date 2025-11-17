---
id: 'TASK-051-REMOVE-ENABLE-CJ-ASSESSMENT-FLAG'
title: 'TASK-051: Remove enable_cj_assessment Flag From Batch Registration'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-08'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-051: Remove enable_cj_assessment Flag From Batch Registration

## Status: PENDING
## Priority: HIGH

## Objective
Eliminate the `enable_cj_assessment` flag from batch registration. Pipelines never auto-run; teachers explicitly request execution later. The flag only pre-populates default pipeline state and metrics but does not gate execution. Removing it simplifies contracts, reduces confusion, and aligns code with actual behavior (request-time resolution + preflight).

## Rationale
- The teacher’s “Run CJ” request is the real trigger. A request can enable CJ even when the flag was false at registration.
- Default pipeline planning at registration time causes drift and duplicate logic (initial state vs. request-time resolution).
- Metrics recorded at registration based on the flag are misleading; the authoritative time to record is preflight/request.
- Removing the flag reduces surface area in contracts, storage, and tests.

## Scope
Refactor API contracts, BOS registration behavior, metrics, and tests to remove or ignore `enable_cj_assessment`. Make request-time pipeline resolution the only source of truth.

## Affected Components (Code + Tests + Docs)

### Shared Contracts
- libs/common_core/src/common_core/api_models/batch_registration.py
  - Field present: `enable_cj_assessment: bool`
  - Related (keep): `cj_default_llm_model`, `cj_default_temperature` (not removed in this task)

### API Gateway
- services/api_gateway_service/routers/batch_routes.py
  - Client model `ClientBatchRegistrationRequest` includes the flag
  - Proxies flag into `BatchRegistrationRequestV1`
  - Registration endpoint docs/examples include the flag
  - Unit tests: services/api_gateway_service/tests/test_batch_registration_proxy.py

### Batch Orchestrator Service (BOS)
- services/batch_orchestrator_service/implementations/batch_processing_service_impl.py
  - Uses flag to add `cj_assessment` to `requested_pipelines` and set CJ status to `PENDING_DEPENDENCIES` vs `SKIPPED_BY_USER_CONFIG`
- services/batch_orchestrator_service/api/batch_routes.py
  - Registration route records pipeline execution metrics based on the flag
  - Status endpoint includes `enable_cj_assessment` in `batch_context`
- services/batch_orchestrator_service/implementations/batch_context_operations.py
  - Persists full registration payload (flag currently stored in `processing_metadata`)
- services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py
  - Updates pipeline state at request time, flips statuses from `SKIPPED_BY_USER_CONFIG` if in resolved pipeline
  - (No direct flag dependency, but status semantics will change)
- BOS tests potentially asserting flag-driven initial statuses:
  - services/batch_orchestrator_service/tests/test_batch_repository_integration.py
  - services/batch_orchestrator_service/tests/unit/test_preflight_route.py
  - services/batch_orchestrator_service/tests/unit/test_batch_class_id_integration.py

### Batch Conductor Service (BCS)
- Pipeline resolution does not use the flag (informational only). No code change anticipated.
  - services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py
  - services/batch_conductor_service/implementations/pipeline_rules_impl.py

### Test Utilities and Functional/Integration Tests
- tests/utils/service_test_manager.py (parameter: `enable_cj_assessment`)
- tests/functional/pipeline_harness_helpers/batch_setup.py
- tests/functional/comprehensive_pipeline_utils.py
- tests/functional/test_e2e_credit_preflight_denial_402.py
- tests/integration/test_pipeline_state_management_progression.py
- tests/integration/test_pipeline_state_management_failures.py
- tests/integration/test_pipeline_state_management_scenarios.py
- tests/integration/test_pipeline_state_management_edge_cases.py (has explicit single-essay case with flag=False)
- services/api_gateway_service/tests/test_batch_registration_proxy.py

### Documentation
- TASKS/TEST_INFRA_ALIGNMENT_BATCH_REGISTRATION.md (References `enable_cj_assessment`)

## Consumers / Callers Summary
- Caller (client): sets flag in AGW request today (UI/API clients)
- AGW consumer/forwarder: passes flag into BOS registration
- BOS consumes flag at registration; BCS ignores; BOS uses request-time resolution when teacher triggers execution

## Strategy — Aggressive, Two Phases

### Phase 1 (Backwards Compatible): Deprecate and Ignore the Flag
Goal: Behavior change with minimal breakage; keep contracts stable but stop using the flag.

1) BOS registration defaults (code change)
- File: services/batch_orchestrator_service/implementations/batch_processing_service_impl.py
  - Stop deriving `requested_pipelines` from `enable_cj_assessment`.
  - Initialize pipeline state neutrally:
    - `requested_pipelines = []`
    - For each known phase: status = `REQUESTED_BY_USER` (or equivalent neutral) instead of SKIPPED vs PENDING.
  - Do not set CJ to `SKIPPED_BY_USER_CONFIG` at registration; leave decision solely to request-time resolution.

2) BOS registration metrics (code change)
- File: services/batch_orchestrator_service/api/batch_routes.py
  - Remove registration-time metrics that count pipelines by flag.
  - Rely on preflight/request-time metrics when a teacher requests execution.

3) Status endpoint (optional now, definitive in Phase 2)
- File: services/batch_orchestrator_service/api/batch_routes.py
  - Keep returning stored `processing_metadata` for compatibility, but document `enable_cj_assessment` as deprecated.

4) Test utilities accept but ignore the flag
- File: tests/utils/service_test_manager.py
  - Leave `enable_cj_assessment` parameter for compatibility; exclude it from payload, or set then explicitly drop at AGW layer in Phase 2.
  - Update docstring to “deprecated; ignored”.

5) Tests: stop relying on initial SKIPPED vs PENDING semantics
- Update tests that asserted flag-driven status:
  - services/batch_orchestrator_service/tests/unit/test_batch_class_id_integration.py
  - services/batch_orchestrator_service/tests/test_batch_repository_integration.py
  - services/batch_orchestrator_service/tests/unit/test_preflight_route.py
  - Replace assertions to reflect neutral initial state and request-time resolution.

6) Docs
- Update TASKS/TEST_INFRA_ALIGNMENT_BATCH_REGISTRATION.md to mark `enable_cj_assessment` deprecated (ignored), and reframe flows around request-time resolution.

7) Back-compat storage
- Keep storing incoming flag in `processing_metadata` for now (no migration), but do not use it.

Acceptance for Phase 1
- All tests pass with neutral initial pipeline state.
- No behavior change at teacher interaction time: “Run CJ” still resolves and runs CJ if valid/allowed.
- No registration-time metrics recorded based on the flag.

### Phase 2 (Breaking): Remove the Flag From Contracts and Code
Goal: Remove from schemas, payloads, status responses, and tests.

1) Remove field from shared contracts
- File: libs/common_core/src/common_core/api_models/batch_registration.py
  - Remove `enable_cj_assessment`.
  - Back-compat: If BOS reconstructs this model from historical DB rows, allow extra keys or adjust deserialization:
    - Option A: set Pydantic model config to allow extras for BOS-only read path, or
    - Option B: change BOS to store/retrieve a dict and avoid strict model validation for legacy rows.

2) API Gateway
- File: services/api_gateway_service/routers/batch_routes.py
  - Remove `enable_cj_assessment` from `ClientBatchRegistrationRequest`.
  - Stop including the field in downstream `BatchRegistrationRequestV1`.
  - Adjust route examples and OpenAPI.
  - Update unit test: services/api_gateway_service/tests/test_batch_registration_proxy.py

3) BOS code and status payload
- Files: 
  - services/batch_orchestrator_service/implementations/batch_processing_service_impl.py (already neutral from Phase 1)
  - services/batch_orchestrator_service/api/batch_routes.py: remove the field from status response completely.
  - services/batch_orchestrator_service/implementations/batch_context_operations.py: keep storing `processing_metadata` without the flag going forward; tolerate legacy metadata with the field.

4) Tests and utilities
- File: tests/utils/service_test_manager.py — remove parameter; fix all call sites:
  - tests/functional/pipeline_harness_helpers/batch_setup.py
  - tests/functional/comprehensive_pipeline_utils.py
  - tests/functional/test_e2e_credit_preflight_denial_402.py
  - tests/integration/test_pipeline_state_management_progression.py
  - tests/integration/test_pipeline_state_management_failures.py
  - tests/integration/test_pipeline_state_management_scenarios.py
  - tests/integration/test_pipeline_state_management_edge_cases.py (ensure single-essay behavior tested via resolved pipeline, not flag)

5) Docs
- TASKS/TEST_INFRA_ALIGNMENT_BATCH_REGISTRATION.md — remove references; describe request-time-only behavior.

Acceptance for Phase 2
- No contract references to `enable_cj_assessment` remain.
- All tests pass without the flag.
- BOS tolerant of legacy DB metadata containing the field.

## Risks & Mitigations
- Legacy rows with `enable_cj_assessment` cause BOS deserialization failures.
  - Mitigation: Allow extras during BOS deserialization or deserialize `processing_metadata` as a dict without strict model validation.
- Tests relying on initial `SKIPPED_BY_USER_CONFIG` need updates.
  - Mitigation: Move assertions to request-time resolution and neutral initial state.
- Client integrations still sending the flag (after Phase 2).
  - Mitigation: AGW should ignore unknown fields at parse time or return a clear validation error during a controlled deprecation window.

## Rollout Plan
- Phase 1 (Deprecate & Ignore): 1–2 days
  - Code changes in BOS, tests, and docs; keep contracts stable
- Bake-in: 1–2 days of normal test runs
- Phase 2 (Removal): 2–3 days
  - Contract removal in common_core and AGW, BOS tolerance for legacy metadata, test sweeping

## Verification
- Unit + integration + functional suites:
  - Preflight 402/429 scenarios unaffected (still evaluated at request time)
  - E2E pipelines still run when requested; CJ consumption events observed and API validates operations
- Metrics:
  - Registration-time pipeline metrics removed; request/preflight metrics intact

## File Checklist (Edit/Remove/Docs)
- [ ] libs/common_core/src/common_core/api_models/batch_registration.py
- [ ] services/api_gateway_service/routers/batch_routes.py
- [ ] services/api_gateway_service/tests/test_batch_registration_proxy.py
- [ ] services/batch_orchestrator_service/implementations/batch_processing_service_impl.py
- [ ] services/batch_orchestrator_service/implementations/batch_context_operations.py (deserialize tolerant)
- [ ] services/batch_orchestrator_service/api/batch_routes.py
- [ ] services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py (status flip semantics awareness)
- [ ] tests/utils/service_test_manager.py
- [ ] tests/functional/pipeline_harness_helpers/batch_setup.py
- [ ] tests/functional/comprehensive_pipeline_utils.py
- [ ] tests/functional/test_e2e_credit_preflight_denial_402.py
- [ ] tests/integration/test_pipeline_state_management_progression.py
- [ ] tests/integration/test_pipeline_state_management_failures.py
- [ ] tests/integration/test_pipeline_state_management_scenarios.py
- [ ] tests/integration/test_pipeline_state_management_edge_cases.py
- [ ] services/batch_orchestrator_service/tests/test_batch_repository_integration.py
- [ ] services/batch_orchestrator_service/tests/unit/test_preflight_route.py
- [ ] services/batch_orchestrator_service/tests/unit/test_batch_class_id_integration.py
- [ ] TASKS/TEST_INFRA_ALIGNMENT_BATCH_REGISTRATION.md

## Notes
- CJ defaults (`cj_default_llm_model`, `cj_default_temperature`) remain supported; they apply when CJ is actually executed, independent of the removed flag.
- This task intentionally does not alter BCS rules; resolution remains purely request/time + dependency-based.

