# DDD Name Propagation Refactor — Thin Events, Clean Boundaries, Personalization at the Edge

## Problem Description

Current contracts leak teacher and student names into orchestration events and command models. This blurs bounded contexts, spreads PII across Kafka, and introduces inconsistency in where names are sourced and maintained. Some fields exist as placeholders (often `None`), creating confusion for implementers and tests, while also raising privacy/staleness risks.

Symptoms:

- `BatchEssaysReady` includes `teacher_first_name`/`teacher_last_name` though ELS cannot own or reliably supply them.
- `BatchServiceAIFeedbackInitiateCommandDataV1` includes optional teacher name fields that BOS does not own and currently sets to `None`.
- `AIFeedbackInputDataV1` mixes in names that should be resolved on demand.
- Tests and logs reference these fields, coupling components to non-essential PII.

Impact:

- Muddled boundaries: BOS/ELS are forced to “know” teacher/student names.
- PII on Kafka: unnecessary propagation of personal data.
- Staleness: names cached in events can diverge from source of truth.
- Developer confusion: placeholder fields encourage accidental use.

## Solution Overview

Adopt a strict thin-event pattern with clean ownership of names:

- Identity Service is the single source of truth for teacher names (PersonNameV1).
- Class Management Service (CMS) is the single source of truth for student names (PersonNameV1).
- BOS/ELS never include names in Kafka events/commands.
- AI Feedback Service resolves names on demand via HTTP:
  - Teacher name via Identity (`owner_user_id` from BOS context)
  - Student names via CMS internal batch endpoint (essay_id → student PersonNameV1)

Contract changes (high-level):

- Remove teacher name fields from `BatchEssaysReady`.
- Replace teacher name fields in `BatchServiceAIFeedbackInitiateCommandDataV1` with `owner_user_id: str`.
- Remove `teacher_name` and `student_name` from `AIFeedbackInputDataV1` (names resolved by the AI Feedback service at runtime; not carried on Kafka).

Security/Privacy posture:

- Keep PII out of Kafka. Names move via HTTP between bounded contexts when needed and only to services that must render them.

Performance posture:

- CMS provides batch endpoint to resolve all essay→student names in one request to avoid N+1.
- Identity profile lookup is a single HTTP GET by user_id.

## Scope and Non‑Goals

In scope:

- Contract removals and renames across common_core and service call sites.
- Identity profiles (storage + endpoints) for teacher names.
- CMS internal endpoints to resolve student names by batch or essay.
- BOS command update to include `owner_user_id` (IDs only).
- AI Feedback integrations to fetch teacher/student names just‑in‑time for prompt curation.

Out of scope (for this task):

- Implementing the full AI Feedback worker pipeline (beyond name resolution scaffolding and client integration points).
- UI changes (frontends can later leverage Identity `display_name`).

## Architecture After Refactor

- Events (Kafka): IDs and orchestration context only — no names.
- BOS: persists batch context, passes `owner_user_id` for downstream consumers.
- ELS: orchestrates thin events, no teacher/student PII on events.
- CMS: authoritative for student names; exposes internal endpoints for batch/essay mapping to PersonNameV1.
- Identity: authoritative for teacher names; persists user profiles; exposes `GET/PUT profile`.
- AI Feedback: resolves names via HTTP and uses them only in prompt creation; does not publish names on Kafka.

## Phases, Steps, and Actionable Items

### Phase 1 — Contracts Cleanup and Call‑Site Updates

Goals:

- Remove teacher name fields from orchestration events.
- Add `owner_user_id` to AI Feedback command.
- Remove name fields from AI Feedback input events.
- Update all call sites and tests; repository compiles and tests pass.

Changes:

- File: `libs/common_core/src/common_core/events/batch_coordination_events.py`
  - Remove fields from `BatchEssaysReady`:
    - `teacher_first_name: str | None`
    - `teacher_last_name: str | None`
- File: `libs/common_core/src/common_core/batch_service_models.py`
  - In `BatchServiceAIFeedbackInitiateCommandDataV1`, remove:
    - `teacher_first_name: str | None`
    - `teacher_last_name: str | None`
  - Add:
    - `owner_user_id: str`  # batch owner user ID (teacher)
- File: `libs/common_core/src/common_core/events/ai_feedback_events.py`
  - In `AIFeedbackInputDataV1`, remove:
    - `teacher_name: str | None`
    - `student_name: str | None`
  - Note: AI Feedback service resolves names via HTTP and does not carry them in events.

Call sites to update (references identified via ripgrep; adjust tests and logs accordingly):

- ELS constructs `BatchEssaysReady`:
  - `services/essay_lifecycle_service/implementations/student_association_handler.py`
  - `services/essay_lifecycle_service/implementations/batch_essay_tracker_impl.py`
- BOS logs/handling of `BatchEssaysReady`:
  - `services/batch_orchestrator_service/implementations/batch_essays_ready_handler.py` (remove teacher name logging)
- BOS AI Feedback initiator (command construction):
  - `services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py`
    - Stop setting teacher names; set `owner_user_id` instead.
- ELS AI Feedback command handling (type changes):
  - `services/essay_lifecycle_service/implementations/batch_command_handler_impl.py`
  - `services/essay_lifecycle_service/protocols.py` (type hints)

Tests to update (non‑exhaustive, based on search):

- `libs/common_core/tests/unit/test_batch_coordination_events_enhanced.py` (teacher fields removed)
- `tests/integration/test_phase1_complete_flow_with_new_state.py` (teacher fields removed)
- BOS tests:
  - `services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.py` (assert `owner_user_id` present; no teacher fields)
  - `services/batch_orchestrator_service/tests/unit/test_event_contracts_v2.py`
  - `services/batch_orchestrator_service/tests/unit/test_dual_event_handling.py`
  - `services/batch_orchestrator_service/tests/unit/test_batch_content_provisioning_completed_handler.py`
  - `services/batch_orchestrator_service/tests/unit/test_batch_dual_event_coordination.py`
  - `services/batch_orchestrator_service/tests/unit/test_idempotency_*` (remove teacher field assertions)
- ELS tests:
  - `services/essay_lifecycle_service/tests/unit/test_dual_event_publishing.py`
  - `services/essay_lifecycle_service/tests/unit/test_batch_command_handler_impl.py`
- Any references to `teacher_first_name`/`teacher_last_name` (search and remove/update).
- Any references to `teacher_name`/`student_name` in `AIFeedbackInputDataV1` in tests or helper utilities.

Acceptance checks:

- `rg -n "teacher_first_name|teacher_last_name"` returns no references outside git history/changelog.
- `rg -n "teacher_name|student_name" libs/common_core/src/common_core/events/ai_feedback_events.py` shows removed fields; no build errors where they were referenced.
- `pdm run typecheck-all`, `pdm run test-all` pass.

Observability and error handling requirements for Phase 1:

- Ensure all affected handlers preserve and log `correlation_id` when refactoring payloads.
- Update logs that referenced removed fields to not imply presence of PII.

### Phase 2 — Identity Profiles (Teacher Names Source of Truth)

Goals:

- Persist teacher names (PersonNameV1 compatible) with display_name and locale.
- Provide HTTP API for name retrieval/update.

Changes:

- DB model & migration:
  - File: `services/identity_service/models_db.py` — add `UserProfile` (FK `users.id`, fields: `first_name`, `last_name`, `display_name`, `locale`, `updated_at`).
  - Alembic migration under `services/identity_service/alembic/versions/*` for `user_profiles` table.
  - Follow existing naming convention: `YYYYMMDD_HHMM_<descriptive_name>.py` (e.g., `20250818_1400_add_user_profiles_table.py`).
- API routes:
  - File: `services/identity_service/api/` (new `profile_routes.py`):
    - `GET /v1/users/{user_id}/profile` → `{ person_name: PersonNameV1, display_name: str | None, locale: str | None }`
    - `PUT /v1/users/{user_id}/profile` → upsert/update names, display_name, locale (auth required per gateway policy).
- DI/repositories:
  - `services/identity_service/implementations/user_profile_repository_sqlalchemy_impl.py` (CRUD)
  - Wire in `services/identity_service/di.py`.

Error handling pattern (use HuleEduError factories):

- Repository methods wrap DB exceptions with `raise_processing_error` and use `raise_resource_not_found` when appropriate. Example:
  - `raise_resource_not_found(service="identity_service", operation="get_user_profile", resource_type="UserProfile", resource_id=user_id, correlation_id=correlation_id)`
  - `raise_processing_error(service="identity_service", operation="update_user_profile", message="Database error", correlation_id=correlation_id, error_type="SQLAlchemyError")`

Import compliance pattern:

- Use `from huleedu_service_libs.error_handling import raise_resource_not_found, raise_processing_error`
- Use `from huleedu_service_libs.resilience import CircuitBreaker`
- Use `from huleedu_service_libs.logging_utils import create_service_logger`
- Follow established import ordering: stdlib, third-party, huleedu_service_libs, common_core, local

DI pattern for HTTP sessions (time-bounded):

- `services/identity_service/di.py`: provide a DI-managed `aiohttp.ClientSession` with `ClientTimeout(total=30)` (Scope.REQUEST), consistent with repository rules.
- Follow established Dishka patterns:

  ```python
  @provide(scope=Scope.REQUEST)
  async def provide_http_session(self) -> AsyncIterator[ClientSession]:
      timeout = ClientTimeout(total=30)
      async with ClientSession(timeout=timeout) as session:
          yield session
  
  @provide(scope=Scope.APP) 
  def provide_profile_handler(self, repository: UserProfileRepositoryProtocol) -> UserProfileHandler:
      return UserProfileHandler(repository)
  ```

Domain handler pattern (future-proof extraction):

- Add `services/identity_service/domain_handlers/profile_handler.py` encapsulating profile logic; routes remain thin and delegate to the handler. This eases future extraction to a dedicated Profile service.

Acceptance checks:

- `GET /v1/users/{user_id}/profile` returns 200 with PersonNameV1 fields when profile exists; 404 or empty defaults otherwise (define behavior in docstring).
- `PUT /v1/users/{user_id}/profile` persists and is reflected in subsequent GET.
- Typecheck/tests pass (add unit tests for repo and routes).

Performance and indexing:

- Add index on `user_profiles.user_id`.
- Add latency metrics for profile GET/PUT and log correlation IDs.

### Phase 3 — CMS Internal Endpoints (Student Names by Batch/Essay)

Goals:

- Provide efficient batch resolution for essay→student PersonNameV1 mappings.

Changes:

- API routes (internal):
  - File: `services/class_management_service/api/` (new `internal_routes.py`):
    - `GET /internal/v1/batches/{batch_id}/student-names` → `[{ essay_id, student_id, student_person_name: PersonNameV1 }]`
    - `GET /internal/v1/associations/essay/{essay_id}` → `{ essay_id, student_id, student_person_name: PersonNameV1 }`
- Repository:
  - Extend Postgres implementation to join `essay_student_associations` → `students` and shape PersonNameV1.
  - Ensure indexes exist on `essay_student_associations.essay_id` and `student_id`.

Error handling pattern:

- Return `[]` for batches without associations.
- On DB exceptions, use `raise_processing_error(service="class_management_service", operation="get_batch_student_names", message=str(e), correlation_id=correlation_id)`.

Performance and indexing:

- Add composite index `essay_student_associations(batch_id, essay_id)` to accelerate batch queries.

Acceptance checks:

- For a batch with confirmed associations, batch endpoint returns all mappings in ≤ 50ms (local dev) for ~30 essays (baseline measurement).
- Unit/integration tests cover no-association and partial-association cases.

### Phase 4 — BOS Command Update (IDs Only)

Goals:

- Pass `owner_user_id` instead of teacher names when initiating AI Feedback.

Changes:

- File: `services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py`
  - On building `BatchServiceAIFeedbackInitiateCommandDataV1`, set:
    - `owner_user_id = batch_context.user_id`
    - Remove teacher name fields.

Acceptance checks:

- BOS unit tests updated to assert `owner_user_id` is present in the command payload.
- No references to teacher name fields remain.

### Phase 5 — AI Feedback Name Resolution Clients

Goals:

- Resolve teacher/person names just‑in‑time for prompt curation; keep names off Kafka.

Changes (service scaffolding):

- Identity client:
  - `services/ai_feedback_service/implementations/identity_client_impl.py` → `get_user_person_name(user_id) -> PersonNameV1`
- CMS client:
  - `services/ai_feedback_service/implementations/cms_client_impl.py` → `get_batch_student_names(batch_id) -> list[{essay_id, student_id, student_person_name}]`
- Prompt workflow integration:
  - Use resolved names in `core_logic/prompt_manager.py` or `context_builder.py`.

HTTP client resilience and observability:

- Wrap all HTTP calls with a `CircuitBreaker` from `huleedu_service_libs.resilience` using standardized configuration:

  ```python
  CircuitBreaker(
      name=f"{service_name}.identity",  # or .cms
      failure_threshold=3,              # Aligned with existing patterns
      recovery_timeout=timedelta(seconds=30),
      success_threshold=2,
      expected_exception=ClientError    # from aiohttp
  )
  ```

- Propagate `X-Correlation-ID`; set `ClientTimeout(total=5)` per request.
- Graceful degradation: if Identity profile 404 → default `PersonNameV1(first_name="Unknown", last_name="Teacher")`; if CMS returns empty → omit student name personalization.
- Metrics: record latency and failure counts; structured logs include batch_id, user_id, correlation_id.

Acceptance checks:

- Unit tests for clients (mock HTTP) and context builder ensuring names flow to prompt composition.
- Ensure no AI Feedback event publishing includes names.

## Affected Files (Enumerated)

Contracts:

- `libs/common_core/src/common_core/events/batch_coordination_events.py` (remove teacher fields)
- `libs/common_core/src/common_core/batch_service_models.py` (add `owner_user_id`, remove teacher fields)
- `libs/common_core/src/common_core/events/ai_feedback_events.py` (remove `teacher_name`, `student_name`)

Service call sites (non‑exhaustive, primary refs):

- BOS
  - `services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py`
  - `services/batch_orchestrator_service/implementations/batch_essays_ready_handler.py` (logging cleanup)
  - Tests under `services/batch_orchestrator_service/tests/**` listed above.
- ELS
  - `services/essay_lifecycle_service/implementations/student_association_handler.py`
  - `services/essay_lifecycle_service/implementations/batch_essay_tracker_impl.py`
  - `services/essay_lifecycle_service/implementations/batch_command_handler_impl.py`
  - Tests under `services/essay_lifecycle_service/tests/**`.
- CMS (new internal API)
  - `services/class_management_service/api/internal_routes.py` (new)
  - Repo updates in `services/class_management_service/implementations/class_repository_postgres_impl.py`
- Identity (profiles)
  - `services/identity_service/models_db.py` (add `UserProfile`)
  - `services/identity_service/api/profile_routes.py` (new)
  - `services/identity_service/di.py`, repo file (new) and migration.
  - `services/identity_service/domain_handlers/profile_handler.py` (new)

Docs/tests/utilities possibly referencing removed fields:

- `libs/common_core/tests/unit/test_batch_coordination_events_enhanced.py`
- `tests/integration/test_phase1_complete_flow_with_new_state.py`
- `docs/API_REFERENCE.md` (if it documents teacher fields in BatchEssaysReady)
- Any markdown/specs referencing teacher names in these events.

## Acceptance Criteria (Checkable Goals)

Functional:

- No fields carrying teacher/student names appear in Kafka event schemas.
- BOS AI Feedback command includes `owner_user_id` and no teacher fields.
- Identity provides `GET/PUT` profile; CMS provides batch/essay internal endpoints.
- AI Feedback uses HTTP to resolve names and never publishes names to Kafka.

Quality Gates:

- `pdm run typecheck-all` passes.
- `pdm run test-all` passes.
- Search checks:
  - `rg -n "teacher_first_name|teacher_last_name"` → 0 results outside docs/changelogs.
  - `rg -n "teacher_name\s*:|student_name\s*:" libs/common_core/src/common_core/events/ai_feedback_events.py` → removed.

Test Organization Standards:

- Unit tests: `test_<component>_unit.py` pattern, placed in `tests/unit/` directories
- Integration tests: `test_<component>_integration.py` pattern, placed in `tests/integration/` directories  
- All new test files must follow established naming and directory conventions
- Circuit breaker failure scenarios covered in integration tests
- HTTP client mocking patterns consistent with existing codebase

Resilience/observability checks:

- HTTP clients include correlation IDs and use CircuitBreaker with expected exception classes.
- Metrics exist for name resolution latency and error rates.
- Graceful fallback behavior covered in tests (defaults returned when dependencies fail).

Performance (dev baseline):

- CMS batch endpoint returns 30‑essay name mapping ≤ 50ms in local environment.

Security/Privacy:

- No PII in Kafka payloads after refactor.

## Rollout Plan

1) Land Phase 1 (contracts + call site updates) in a single PR; ensure all tests green.
2) Land Phase 2 (Identity profiles) with unit/integration tests.
3) Land Phase 3 (CMS internal endpoints) with tests and index verification.
4) Land Phase 4 (BOS owner_user_id) + corresponding tests.
5) Land Phase 5 (AI Feedback clients + integration points — stubbed if full service not active).

Post‑merge verification:

- Re-run E2E functional tests for pipeline initiation and Phase 1/2 flows.
- Verify no teacher/student names appear in Kafka payload samples/logs.
- Verify CMS batch endpoint performance and Identity profile GET latency meet baselines.

## Notes and Rationale

- Using PersonNameV1 universally for profiles aligns with existing `Student` modeling and keeps semantics consistent.
- Keeping names off Kafka reduces PII handling scope and avoids stale projections.
- Centralizing name resolution in AI Feedback keeps personalization concerns local to where they’re needed and maintains clean service boundaries.

## Contract Documentation Refinements

- `libs/common_core/src/common_core/batch_service_models.py`
  - `class BatchServiceAIFeedbackInitiateCommandDataV1(BaseEventData)`
    - Field docs: `owner_user_id` → “User ID of batch owner (teacher). Names are resolved by AI Feedback via Identity; not transmitted on Kafka.”
- `libs/common_core/src/common_core/events/batch_coordination_events.py`
  - `class BatchEssaysReady` no longer includes teacher fields; downstream services must not rely on them.
- `libs/common_core/src/common_core/events/ai_feedback_events.py`
  - `class AIFeedbackInputDataV1` no longer includes `teacher_name` or `student_name`; these are resolved at consumption time and used internally only.
