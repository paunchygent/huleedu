# Task: Test Infrastructure Alignment for Batch Registration via API Gateway (Revised)

## Executive Summary
Align cross-cutting functional/E2E test infrastructure with the architectural shift that makes the API Gateway (AGW) the single client-facing entry point for batch registration. Identity is injected at the edge (AGW) and threaded org-first through BOS → ELS → downstream services and events. This task delivers a phased migration of test utilities and harnesses to validate AGW proxy behavior, identity threading, and correlation preservation while preserving service-scoped integration tests that exercise internals.

## Problem Statement
Recent architecture changes established AGW as the boundary for client requests and identity injection, with org-first identity threading used for entitlements and attribution. However, many functional and E2E tests still:
- Call BOS directly for registration (bypassing AGW and identity injection).
- Embed identity in request bodies (contradicting edge injection via AGW).
- Lack coverage for JWT org-claim variations (org_id | org | organization_id).
- Do not validate identity header forwarding and `EventEnvelope.metadata["org_id"]`.

This misalignment obscures regressions at the edge, weakens contract fidelity, and fails to validate org-first identity semantics that downstream services rely upon.

## Architectural Analysis & Rationale
- Edge identity injection is the source of truth (Rules: 020.10 API Gateway, 042 Proxy Patterns). Tests representing client flows must enter via AGW and validate identity threading.
- Integration tests that mock BOS internals are valuable and should remain at their abstraction level (Rules: 070, 075). They must not be rewritten to use AGW.
- JWT org claim names are configurable (config default: ["org_id", "org", "organization_id"]). Tests must verify extraction precedence to prevent production drift.
- Correlation must be preserved end-to-end; both proxy headers and envelope metadata must reflect it.

## Scope
In scope:
- Functional/E2E harness and utilities used for client-like flows (batch registration, file uploads, class management, client pipeline requests).
- Identity validation utilities and JWT helpers for claim variation testing.
- Limited updates to functional tests to use AGW for registration and to assert identity threading.

Out of scope (unchanged):
- Service-scoped unit tests and integration tests that mock internals (e.g., BOS handlers, CJ publisher logic). These retain direct calls or mock-based flows per Rule 070/075.

## Affected Files & Artifacts
Utilities and harness
- tests/utils/service_test_manager.py (add AGW endpoint; add create_batch_via_agw())
- tests/utils/auth_manager.py (new helpers: create_individual_user, create_org_user, generate_jwt_with_org_claim)
- tests/utils/identity_validation.py (new) – header and envelope metadata validators
- tests/functional/pipeline_test_harness.py (switch registration via AGW; pass explicit user)
- tests/functional/comprehensive_pipeline_utils.py (registration helper via AGW)

Functional/E2E tests (client-like flows)
- tests/functional/test_e2e_file_workflows.py (create batch via AGW; optional file upload via AGW when validating proxy)
- tests/functional/test_e2e_identity_threading.py (fix user propagation; assert identity metadata)
- tests/functional/test_e2e_* that register batches or assert identity/correlation

Integration tests (internal mocking)
- No API entrypoint changes. Keep direct BOS/internal flows (e.g., tests/integration/test_phase1_student_matching_integration.py, tests/integration/test_cj_entitlements_identity_flow.py). Only add assertions for envelope metadata where applicable.

Related service contracts & routes (no changes; reference for parity)
- libs/common_core/src/common_core/api_models/batch_registration.py
- services/api_gateway_service/routers/batch_routes.py (register; identity injection)
- services/api_gateway_service/routers/file_routes.py (header forwarding)
- services/api_gateway_service/routers/class_routes.py (proxy identity forwarding)
- services/batch_orchestrator_service/api/batch_routes.py (BOS registration receiver)

Repository rules referenced
- .cursor/rules/015-project-structure-standards.mdc
- .cursor/rules/020-architectural-mandates.mdc
- .cursor/rules/020.10-api-gateway-service.mdc
- .cursor/rules/020.17-entitlements-service-architecture.mdc (ensure listed in 000 index)
- .cursor/rules/030-event-driven-architecture-eda-standards.mdc
- .cursor/rules/042-http-proxy-service-patterns.mdc
- .cursor/rules/050-python-coding-standards.mdc
- .cursor/rules/070-testing-and-quality-assurance.mdc
- .cursor/rules/075-test-creation-methodology.mdc
- .cursor/rules/080-repository-workflow-and-tooling.mdc
- .cursor/rules/090-documentation-standards.mdc

Ancillary documentation update
- .cursor/rules/000-rule-index.mdc → Add entry for .cursor/rules/020.17-entitlements-service-architecture.mdc

## Design Decisions
1) Client-like tests must use AGW for registration and class/file operations to validate edge identity injection and proxy behavior.
2) Maintain isolation for service-scoped integration tests to avoid mixed abstraction levels.
3) Introduce explicit identity validation utilities to keep assertions focused and reusable.
4) Phase migration to avoid breaking tests that rely on BOS-specific payloads, flipping defaults only after confidence.

## Phased Implementation Plan

Phase 1 — Non‑breaking Additions (greenfield alongside existing)
- Utilities
  - Add AGW endpoint to ServiceTestManager.SERVICE_ENDPOINTS (port 8080).
  - Implement ServiceTestManager.create_batch_via_agw(...):
    - POST http://localhost:8080/v1/batches/register
    - Remove user_id from body (AGW injects via Authorization)
    - Provide Authorization: Bearer <jwt>, and X-Correlation-ID
    - Support optional class_id and enable_cj_assessment
  - Enhance AuthTestManager:
    - create_individual_user() (no org claim)
    - create_org_user(org_id=...)
    - generate_jwt_with_org_claim(user, claim_name in [org_id|org|organization_id])
  - New tests/utils/identity_validation.py:
    - validate_proxy_headers(headers): X-User-ID, optional X-Org-ID, X-Correlation-ID
    - validate_event_metadata(envelope): assert metadata["org_id"]
    - validate_batch_registration_identity(response): consistency checks
    - validate_agw_registration_identity(agw_response): assert AGW identity semantics (org/user, correlation)
    - validate_event_identity(envelope): focused event identity assertion helper
    - Optional (service-scoped integration only): validate_identity_consistency(agw_response, event_envelope, db_record) — composite validator for targeted tests; avoid in cross-cutting functional tests to prevent abstraction mixing per Rules 070/075
- AGW Class Management proxy tests
  - Add an AGW service-level test (in services/api_gateway_service/tests) that mocks the downstream `httpx` client via DI and asserts forwarding of `X-User-ID`, optional `X-Org-ID`, and `X-Correlation-ID` for `/v1/classes/*` proxy routes (fast, isolated)
- Metrics helpers (non-identity)
  - Add root test helpers to validate proxy and downstream call metrics counters/timers increment (e.g., http_requests_total, downstream_service_calls_total, durations)
  - Important: do NOT include identity values as metric labels (avoid high-cardinality/PII) per observability rules; validate presence/shape only
- New functional tests (additive)
  - test_org_batch_flow() – register via AGW with org user; verify headers/envelope
  - test_individual_batch_flow() – register via AGW with individual user; metadata None
  - test_org_claim_variations() – parametrize claim names and assert extraction precedence

Checkpoints
- CP1.1: New AGW utilities implemented and unit‑smoke verified
- CP1.2: New identity validation utilities available
- CP1.3: New functional tests pass locally against running stack
- CP1.4: AGW class proxy header-forwarding service test passing
- CP1.5: Metrics helper validations passing without identity labels

Phase 2 — Migration (functional/E2E harness adoption)
- Update functional harness and helpers to use AGW:
  - tests/functional/pipeline_test_harness.py → call create_batch_via_agw()
  - tests/functional/comprehensive_pipeline_utils.py → registration via AGW helper
  - tests/functional/test_e2e_file_workflows.py → create batch via AGW; optionally route uploads via AGW when validating proxy
  - Fix bug in tests/functional/test_e2e_identity_threading.py: pass created user to setup_* methods so identity assertions match
- Keep integration tests that mock internal handlers unchanged (no AGW rewrite)
- Optional functional proxy test
  - Add a lightweight functional test that calls AGW `/v1/classes/*` and validates successful proxy behavior end-to-end (without raw header capture); retain header-assertions in the AGW service-level test for precision

Checkpoints
- CP2.1: Pipeline harness uses AGW for registration
- CP2.2: Identity threading E2E tests stable; correlation preserved
- CP2.3: Unit + integration suites green; typecheck clean

Phase 3 — Default Flip + Cleanup
- Switch ServiceTestManager.create_batch() default to AGW and deprecate/remove BOS‑direct path after stability confirmed
- Remove any deprecated BOS‑only registration helpers from functional codepaths
- Update tests/README.md and TASKS references to codify AGW entry for client flows
- Update .cursor/rules/000-rule-index.mdc to include 020.17 (if not already in index)

Checkpoints
- CP3.1: Default create_batch → AGW without regressions
- CP3.2: Documentation updated
- CP3.3: CI suite stable for 2 consecutive runs

## Detailed Work Items (by file)

tests/utils/service_test_manager.py
- Add ServiceEndpoint("api_gateway_service", 8080, has_http_api=True, has_metrics=True)
- Add async create_batch_via_agw(expected_essay_count, course_code, user, correlation_id, enable_cj_assessment, class_id=None):
  - Build client-facing model (no identity fields) per AGW batch_routes ClientBatchRegistrationRequest
  - Set Authorization header from AuthTestManager; include X-Correlation-ID
  - POST to http://localhost:8080/v1/batches/register; expect 202 with batch_id and correlation_id
- Do not change create_batch() default in Phase 1; flip in Phase 3

tests/utils/auth_manager.py
- Add create_individual_user() that does not set any organization_id claim
- Add create_org_user(org_id: str)
- Add generate_jwt_with_org_claim(user, claim_name: Literal["org_id", "org", "organization_id"]) to exercise AGW claim precedence
- Optional: get_auth_headers(user, via_proxy=True|False) to control headers for AGW vs internal service calls

tests/utils/identity_validation.py (new)
- IdentityValidator.validate_proxy_headers(response_headers) → asserts X-User-ID, optional X-Org-ID, X-Correlation-ID
- IdentityValidator.validate_event_metadata(envelope_dict) → asserts metadata.org_id threading
- IdentityValidator.validate_batch_registration_identity(response_json) → sanity checks for registration identity/correlation

tests/functional/pipeline_test_harness.py
- Use create_batch_via_agw() for registration; ensure the same user is passed to setup methods
- Preserve existing Kafka monitoring logic; assert identity via identity_validation utilities where applicable

tests/functional/comprehensive_pipeline_utils.py
- Update register_comprehensive_batch(...) to call ServiceTestManager.create_batch_via_agw(...)

tests/functional/test_e2e_file_workflows.py
- Create batch via AGW; for proxy validation scenarios, upload via AGW file route; otherwise keep direct File Service path for service-specific tests (explicitly marked)

services/api_gateway_service/tests (new or extended)
- Add class proxy identity header-forwarding test using DI to inject a mock httpx client and assert `X-User-ID`, optional `X-Org-ID`, and `X-Correlation-ID` are forwarded

tests/functional/test_e2e_identity_threading.py
- Pass the created test user to harness setup methods so ResourceConsumptionV1 identity assertions match
- Add assertion that EventEnvelope.metadata["org_id"] is set for org flows and None for individuals

Integration tests (unchanged entry)
- tests/integration/test_cj_entitlements_identity_flow.py – already asserts identity in ResourceConsumptionV1
- tests/integration/test_phase1_student_matching_integration.py – keep mocking BOS internals; do not switch to AGW

Documentation and rules
- Update .cursor/rules/000-rule-index.mdc with 020.17 entitlements architecture
- Ensure references to Rule 042 proxy patterns and Rule 020.10 AGW in test docs where rationale is cited
 - Observability guidance: ensure tests adhere to 071-observability standards (no identity labels in metrics) when adding metrics assertions

## Acceptance Criteria
- All functional/E2E tests that represent client flows perform registration via AGW (no direct BOS registration in those tests)
- Identity threading validated:
  - JWT org-claim extraction precedence (org_id | org | organization_id)
  - Proxy headers present where applicable (File, Class routes)
  - EventEnvelope.metadata["org_id"] set for org flows; None for individual flows
- Correlation integrity validated end-to-end for registration and pipeline requests
- Integration tests that mock internals remain at their abstraction level and pass
- AGW class proxy identity header-forwarding service test passes and is stable
- Typecheck and tests green:
  - pdm run typecheck-all
  - pdm run test-unit
  - pdm run test-integration (targeted selection)
  - pdm run test-cov (optional)

## Non‑Goals
- No contract/schema changes; tests reflect existing shared contracts in common_core
- No redesign of service internals or DI; only test infrastructure alignment

## Risks & Mitigations
- Risk: Breaking tests that rely on BOS‑specific payloads
  - Mitigation: Add create_batch_via_agw() alongside existing method; migrate harness first; flip default only in Phase 3
- Risk: Mixing abstraction levels
  - Mitigation: Keep service-scoped integration tests unchanged; scope AGW use to client-like flows only
- Risk: Flaky correlation assertions
  - Mitigation: Always pass and assert X-Correlation-ID from AGW response through envelopes; start consumers before triggering events
- Risk: JWT claim ambiguity
  - Mitigation: Parametric tests cover configured claim order; add generate_jwt_with_org_claim to exercise precedence

## Verification Plan
Local/dev run prerequisites
- Ensure Docker stack is up and healthy: `pdm run up` (or `pdm run dev dev`), validate AGW at http://localhost:8080/healthz
- Source environment if direct docker exec is needed: `source .env`

Targeted runs during migration
- pdm run pytest tests/utils -q
- pdm run pytest tests/functional/test_e2e_identity_threading.py -q
- pdm run pytest tests/functional/test_e2e_file_workflows.py -q
- pdm run pytest tests/functional/pipeline_test_harness.py -q
- (from AGW service dir) pdm run pytest services/api_gateway_service/tests -q  # class proxy header test

Full quality gates
- pdm run typecheck-all
- pdm run test-unit
- pdm run test-integration
- pdm run test-all (optional in CI)

## Success Metrics & Checkpoints
- CP1.x completed and passing locally within 1 day of kickoff
- CP2.x completed with no regression in unrelated suites; identity assertions stable
- CP3.x completed; create_batch default flipped to AGW; 2 consecutive green CI runs

## References
- Services & Contracts:
  - services/api_gateway_service/routers/batch_routes.py
  - services/api_gateway_service/routers/file_routes.py
  - services/api_gateway_service/routers/class_routes.py
  - services/batch_orchestrator_service/api/batch_routes.py
  - libs/common_core/src/common_core/api_models/batch_registration.py
- Rules:
  - .cursor/rules/015-project-structure-standards.mdc
  - .cursor/rules/020-architectural-mandates.mdc
  - .cursor/rules/020.10-api-gateway-service.mdc
  - .cursor/rules/020.17-entitlements-service-architecture.mdc
  - .cursor/rules/030-event-driven-architecture-eda-standards.mdc
  - .cursor/rules/042-http-proxy-service-patterns.mdc
  - .cursor/rules/050-python-coding-standards.mdc
  - .cursor/rules/070-testing-and-quality-assurance.mdc
  - .cursor/rules/075-test-creation-methodology.mdc
  - .cursor/rules/080-repository-workflow-and-tooling.mdc
  - .cursor/rules/090-documentation-standards.mdc
  - .cursor/rules/071-observability-index.mdc
  - .cursor/rules/071.1-prometheus-metrics-patterns.mdc
