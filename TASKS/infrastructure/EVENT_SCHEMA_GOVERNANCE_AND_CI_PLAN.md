# Event Schema Governance & CI Gate (Weeks 6–8)

Objective
- Enforce versioned event contracts with automated compatibility checks in CI.

Scope
- In: JSON Schema (or Avro) definitions for top events, registry repo folder, CI validation, contract tests.
- Out: External schema registry service (use repo-based registry initially).

References
- Schemas: `libs/common_core/src/common_core/events/*`, `event_enums.py`, `envelope.py`
- CI: `pyproject.toml` (add script), GitHub Actions (if used), tests in `tests/contract/*`
- Rules: `052-event-contract-standards.mdc`, `070-testing-and-quality-assurance.mdc`

Deliverables
1. Schema directory: `libs/common_core/schemas/events/*.json` (or Avro), versioned per event (v1, v2, ...).
2. Validation tool: script to validate sample payloads from tests against schemas.
3. CI check: block PRs with breaking changes unless version bumped.
4. Contract tests expanded to generate payloads and validate against schema.

Work Packages
1) Bootstrap Schemas
   - Define schemas for: BatchCreated/BATCH_ESSAYS_REGISTERED, ESSAY_SPELLCHECK_COMPLETED, BATCH_NLP_ANALYSIS_COMPLETED, CJ_ASSESSMENT_COMPLETED, BATCH_RESULTS_READY, BatchAuthorMatchesSuggestedV1.
   - Acceptance: Schemas validated; sample payloads pass.

2) Validation Script
   - `scripts/validate_event_schemas.py` to load schemas and validate payloads (jsonschema or fastavro).
   - `pdm run` script alias; integrate in `test-all` or dedicated.
   - Acceptance: Non-conformant payloads fail CI.

3) CI Gate
   - Add job to run schema validation and diff-check for breaking changes (field removals/type narrowing).
   - Acceptance: PR blocked on breaking change unless version bumped in event name and schema file.

4) Tests
   - Extend `tests/contract/` to emit example envelopes and validate via script.

Definition of Done
- Schemas exist for top events; CI blocks breaking changes; tests validate payloads against schemas.
