# TASK: Phase 3.2 – Prompt Architecture Implementation

**Status**: PLANNED  
**Priority**: HIGH  
**Estimated Effort**: 4–6 weeks  
**Assignee**: TBD

## Quick Reference

- **Parent**: `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`
- **Depends On**: Phase 3.1 – Grade Scale Registry (COMPLETE)
- **Blocks**: Phase 3.3 – ENG5 NP Batch Tooling
- **Decision Baseline**: Registration must *not* require `assignment_id` or inline prompts; student prompts are stored as Content Service references; canonical CJ owns system prompts and assignments.

## Executive Summary

The objective is to decouple student prompt payloads from registration forms while preserving canonical CJ integrity and respecting service ownership boundaries. BOS and Gateway inputs will accept either canonical CJ assignments (`assignment_id`) or CMS-owned Content Service references (`cms_prompt_ref`), with prompt-dependent phases gated by BCS until a reference is attached. CMS manages ad-hoc prompt references, CJ exposes canonical prompt metadata, and downstream services (NLP, AI Feedback) consume prompt references rather than raw text.

## Discovery Checklist

- [x] Locate registration DTOs in API Gateway (`docs/api-types.ts`, FastAPI handlers) and BOS to confirm current `assignment_id` / prompt reference requirements; capture file paths.
- [x] Inspect CJ data access (`assessment_instructions`, repositories, migrations) for canonical prompt storage and versioning.
- [x] Audit prompt usage in NLP and AI Feedback services to map where prompt references are propagated.
- [x] Review BCS gating configuration to identify how batch prerequisites are stored (e.g., Redis projection vs. BOS state) and determine extension point for a `prompt_attached` flag.
- [x] Inventory Content Service client usage patterns, including required auth scopes and hash validation.
- [x] Document relevant service ports/endpoints for local manual testing.
- [x] Persist findings in `TASKS/notes/phase_3_2_discovery.md`.

## Implementation Plan

1. **Gateway & BOS DTO Adjustments** (1.0–1.5 weeks)  
   - Make registration time `assignment_id` optional; replace inline prompt payloads with Content Service references.  
   - Introduce prompt-dependent pipeline discriminated union (`{assignment_id}` vs `{cms_prompt_ref}`) using canonical `PhaseName`.  
   - Enforce BOS validation: canonical runs forbid teacher prompt references; ad-hoc runs must provide `cms_prompt_ref`.  
   - Update persistence to store only references plus content hash.

2. **BCS Prompt Gating** (0.5–1.0 week)  
   - Extend `BCSPipelineDefinitionRequestV1` and BCS client calls with a `batch_metadata` payload carrying `prompt_attached`.  
   - Fail prompt-dependent pipelines in `validate_pipeline_compatibility` when metadata indicates no prompt; emit metric `bcs_prompt_prerequisite_blocked_total`.  
   - Add tests covering blocked vs allowed transitions.

3. **CMS Prompt Reference Lifecycle** (1.0–1.5 weeks)  
   - Implement attach (`POST /v1/teacher-registrations/{id}/prompt`) and lock endpoints, persisting Content Service references only.  
   - Integrate Content Service auth verification and hash validation.  
   - Emit `TeacherPromptAttachedV1` / `TeacherPromptLockedV1` events if the lifecycle bus exists, otherwise document deferred eventing.  
   - Add unit/integration coverage.

4. **CJ Assessment Read APIs & Admin Surface** (0.5–1.0 week)  
   - Expose read-only endpoint `GET /v1/cj-assignments/{assignment_id}/latest` returning `student_prompt_ref`, `grade_scale`, `anchor_set_present`, and version metadata when available.  
   - Wire to existing repositories; avoid schema invention.  
   - Align admin CRUD (if present/planned) with grade-scale registry for managing judge prompts.  
   - Cover with unit tests.

5. **Downstream Consumer Updates (NLP, AI Feedback)** (0.5 week)  
   - Adapt services to resolve Content Service references on demand and discard blobs after use.  
   - Add fake-client unit tests ensuring only references cross service boundaries.
   - Detailed migration steps for NLP & CJ services tracked in [child prompt-reference consumer migration plan](TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.child-prompt-reference-consumer-migration.md).

6. **Event & Observability Updates** (0.5 week)  
   - Ensure new events use `EventEnvelope` and `StorageReferenceMetadata`.  
   - Add BOS validation metric `bos_prompt_invariant_violations_total{reason=…}`.  
   - Draft ADR “Prompt Ownership and Content References” in `documentation/`.

## Testing Strategy

- Unit tests for Gateway DTO parsing, BOS validation paths, BCS gating logic, CMS prompt endpoints, CJ read endpoints, and downstream reference consumers.
- Contract / schema tests for any new or broadened events.  
- Integration tests simulating batch registration through prompt-dependent phase start (happy path and invariant violation).
- Manual smoke: run `pdm run dev-start bos_service bcs_service class_management_service cj_assessment_service content_service` and execute representative API flows with prompt attachment/locking.
- CI commands:  
  - `pdm run pytest-root services/batch_orchestrator_service -k prompt --maxfail=1`  
  - `pdm run pytest-root services/batch_conductor_service -k prompt --maxfail=1`  
  - `pdm run pytest-root services/class_management_service -k prompt --maxfail=1`  
  - `pdm run pytest-root services/cj_assessment_service -k assignment --maxfail=1`

## Acceptance Criteria

- Registration APIs accept optional `assignment_id`; inline prompts removed from canonical payloads.  
- Prompt-dependent pipelines require either canonical assignment or CMS reference; violating requests are rejected with explicit BOS errors.  
- BCS enforces `prompt_attached` gating prior to starting `cj_assessment`, `ai_feedback`, or prompt-dependent NLP phases.  
- CMS stores and locks Content Service references, with hashes persisted and exposed via read APIs/events.  
- CJ exposes canonical assignment metadata (prompt reference, grade scale, anchor presence) through a stable read endpoint.  
- NLP and AI Feedback operate on prompt references without persisting prompt bodies.  
- Observability includes metrics for BOS/BCS prompt invariants, and documentation reflects the new ownership model.  
- Prototype scope confirmed: no backward-compat path required; a single cutover to reference-based payloads is acceptable.

## Risks & Mitigations

- **BCS State Ambiguity**: Clarify during discovery whether BOS or BCS owns the new flag; document and align storage early to avoid double writes.  
  *Mitigation*: Prototype flag propagation in a feature branch once discovery confirms data flow.  
- **Content Service Auth/Hash Drift**: Incorrect reference validation could block prompts.  
  *Mitigation*: Extend discovery notes with auth scope details; add hash verification tests.  
- **Event Schema Evolution**: Introducing prompt reference fields may break consumers.  
  *Mitigation*: Use optional fields with versioned events and document migration path.  
- **Prototype Cutover Risk**: Hard switch to references means in-flight tests must be updated simultaneously.  
  *Mitigation*: Stage a single branch/PR that updates contracts, fixtures, and service consumers together; communicate timing to all contributors.

## Out of Scope

- Changes to Phase 1 student matching workflows.  
- Modifying event envelope format or observability infrastructure beyond new metrics.  
- Redesigning Content Service storage semantics or BOS/BCS core architecture.  
- Altering canonical CJ anchor datasets beyond exposing existing metadata.

## Progress Log

- **2025-11-05** – Core contract refactor kicked off  
  - Updated `libs/common_core` events and batch service models to replace `essay_instructions` with `student_prompt_ref`; added `ContentType.STUDENT_PROMPT_TEXT`.  
  - Gateway/BOS registration, pipeline DTOs, and persistence now operate on prompt references; pipeline requests carry a `prompt_payload` union and BOS emits `batch_metadata` when calling BCS.  
  - BCS accepts the new metadata, enforces prompt prerequisites via `validate_pipeline_compatibility`, and records violations with `huleedu_bcs_prompt_prerequisite_blocked_total`.  
- **2025-11-05** – ELS persistence wired for prompt references  
  - `BatchExpectation` and database persistence now store `student_prompt_ref`, and recovery paths deserialize references from `batch_metadata`.  
  - `BatchEssaysReady` events emitted by ELS carry `student_prompt_ref`, ensuring downstream consumers receive the reference during readiness handoff.  
  - Added targeted BOS unit tests to verify prompt metadata plumbing and fixed the pipeline guard regression that blocked sequential runs.  
  - Remaining work: hydrate prompt text through ELS dispatchers using Content Service, adapt NLP/CJ services to consume references directly, update fixtures/docs, and retire bridging/legacy `essay_instructions` support as soon as downstream migrations are complete. **(Superseded by 2025-11-06 / 2025-11-08 entries below.)**

- **2025-11-05** – ELS dispatcher bridging complete (Step 3)
  - Implemented Content Service prompt hydration in `DefaultSpecializedServiceRequestDispatcher` with fallback to legacy text
  - Added `ContentServiceClient` to ELS DI container (APP scope) with proper configuration from settings
  - Updated command handlers (NLP, CJ) to retrieve `student_prompt_ref` from batch context via `BatchEssayTracker.get_batch_status()`
  - Enhanced `get_batch_status()` to deserialize and expose `student_prompt_ref` from `batch_metadata`
  - Implemented `_fetch_prompt_text()` helper with structured error handling, logging, and metric tracking
  - Added `huleedu_els_prompt_fetch_failures_total{context="nlp|cj"}` metric for observability
  - Updated dispatcher protocols to accept optional `student_prompt_ref` parameter
  - Fixed all 3 target test suites: `test_nlp_command_handler.py`, `test_cj_assessment_command_handler.py`, `test_kafka_circuit_breaker_business_impact.py`
  - **Next**: Migrate NLP and CJ services to consume `student_prompt_ref` natively, then remove dispatcher bridging

- **2025-11-06** – Downstream consumer migration & dispatcher cleanup (Steps 3–4 wrap-up)
  - NLP and CJ services now fetch prompts directly from Content Service, emit `huleedu_{nlp|cj}_prompt_fetch_failures_total`, and persist prompt metadata without inline strings.
  - Essay Lifecycle dispatcher no longer hydrates prompt text; prompt metadata flows exclusively via `StorageReferenceMetadata`.
  - Alembic migrations `20251106_1845_make_cj_prompt_nullable.py` and `20251106_2105_remove_essay_instructions.py` removed residual prompt columns.
  - Service READMEs plus Grafana playbook updated with prompt reference flows and new metrics.

- **2025-11-08** – Cross-service validation & doc/test refresh (Step 5)
  - Updated discovery notes, handoff, and task plan to reflect the reference-only prompt architecture and completed validation.
  - Refreshed API Gateway + BOS unit suites to build payloads with `student_prompt_ref`, eliminating silent acceptance of legacy `essay_instructions`.
  - Executed targeted pytest runs (`services/api_gateway_service/tests/test_batch_registration_proxy.py`, `services/batch_orchestrator_service/tests -k "prompt or idempotency or batch_context"`) plus linted docs to enforce the new contract end-to-end.
  - Result Aggregator now persists `student_prompt_ref` inside `batch_results.batch_metadata`, with documentation in `services/result_aggregator_service/README.md` and integration tests covering round-trips.

### Next Steps
- Result Aggregator API responses (`/internal/v1/batches/...`) now surface `student_prompt_ref`; coordinate with dashboard/BI owners if they need to render prompt provenance.
- Align Result Aggregator functional fixtures (Result Aggregator + end-to-end suites) with the new metadata once AI Feedback notebooks consume `student_prompt_ref`.

### Dispatcher Bridging Rules

Legacy bridging logic was removed on 2025-11-06 once NLP and CJ services became reference-native. ELS now forwards `student_prompt_ref` exclusively; no prompt hydration occurs within the dispatcher.
