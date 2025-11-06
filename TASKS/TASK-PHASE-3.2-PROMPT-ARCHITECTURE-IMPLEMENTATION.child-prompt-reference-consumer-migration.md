# Child Task: Prompt Reference Consumer Migration (Phase 3.2)

**Parent**: [TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md](TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md)

## Purpose
Complete the downstream prompt-reference migration by shifting all services from dispatcher-hydrated `essay_instructions` strings to Content Service references. This task executes the plan in staged increments so each downstream service can be migrated with focused validation.

## Scope & Phasing
1. **Common Core Contracts**
   - Extend `BatchNlpProcessingRequestedV2` and `ELS_CJAssessmentRequestV1` to include `student_prompt_ref: StorageReferenceMetadata | None`.
   - Remove legacy `essay_instructions` fields and validators.
   - Update shared fixtures/tests and regenerate documentation snippets if any.

2. **Essay Lifecycle Service (Dispatcher & Metrics)**
   - Remove `_fetch_prompt_text` bridging logic and associated metrics.
   - Ensure Phase 3.2 handlers pass `student_prompt_ref` to downstream events without hydrated text.
   - Update migrations/models so persisted `essay_instructions` columns are nullable.

3. **NLP Service Consumer (Phase 2)**
   - Hydrate prompts via Content Service client, add failure metric/logging, and propagate optional prompt text downstream.
   - Adapt tests/fixtures to provide references and mock Content Service responses.

4. **CJ Assessment Service Consumer**
   - Fetch prompts via Content Service, add failure metric/logging, and persist nullable prompt text.
   - Update workflow modules, repositories, and tests to accept optional prompt text.

5. **Validation & Documentation**
   - Run targeted pytest suites (`services/nlp_service`, `services/cj_assessment_service`, relevant ELS unit tests) plus mypy for touched services.
   - Update service READMEs, metrics descriptions, and Phase 3.2 task checklist.
   - Update `.claude/HANDOFF.md` with completed steps, residual risks, and next actions.

## Current Status (2025-11-06)
- [x] Step 1 – Common Core contracts updated to carry `student_prompt_ref` (2025-11-04 session).
- [x] Step 2 – Essay Lifecycle dispatcher now forwards references only (2025-11-06 session kickoff).
- [x] Step 3 – NLP service hydrates prompt text locally, exposes `huleedu_nlp_prompt_fetch_failures_total`, and propagates `student_prompt_text`/`student_prompt_storage_id` via event metadata. Updated handler, protocols, event publisher, and unit tests (`pdm run pytest-root services/nlp_service/tests -k batch_nlp_analysis_handler`).
- [x] Step 4 – CJ assessment service now hydrates prompts, emits `huleedu_cj_prompt_fetch_failures_total{reason=…}`, stores nullable prompt metadata, and ships Alembic migration `20251106_1845_make_cj_prompt_nullable.py`. Updated workflow/repository/protocols/tests; validated with `pdm run pytest-root services/cj_assessment_service/tests -k 'event_processor or batch_preparation'` and `pdm run typecheck-all`.
- [ ] Step 5 – Cross-service validation, documentation refresh, and residual search still outstanding.

**Post-migration cleanup TODO (after all producers use enum keys + backfill complete):**
- Remove the temporary string-key fallback in NLP/CJ prompt hydration once storage refs are guaranteed to be keyed by `ContentType`.
- Reset CJ dev databases after deploying the nullable migration instead of backfilling legacy `essay_instructions` rows (sandbox data only).

## Deliverables
- Updated common-core event contracts and dependent fixtures.
- Refactored ELS dispatcher and metrics eliminating prompt hydration.
- NLP and CJ services consuming prompt references directly with new metrics.
- Migration/state updates for nullable `essay_instructions`.
- Documentation updates (service READMEs, task logs, handoff).

## Risks & Mitigations
- **Breaking Change Propagation**: Removing `essay_instructions` is breaking; execute in order (contracts → ELS → consumers) and gate each phase with tests.
- **Content Service dependencies**: Mock/fake clients must cover new fetch paths; add failure metrics to surface runtime issues early.
- **Database nullability**: Coordinate with pending migration (`20251105_2230_make_essay_instructions_nullable.py`) to avoid divergence between ORM and schema.

## Completion Criteria
- All downstream services rely on `student_prompt_ref` and fetch prompt text locally.
- No remaining references to dispatcher prompt hydration logic.
- Metrics dashboards include NLP/CJ prompt fetch failure counters; ELS counter retired.
- Phase 3.2 prompt architecture checklist reflects downstream migration completion.
- Handoff documentation captures final state and any outstanding follow-ups (e.g., AI Feedback).
