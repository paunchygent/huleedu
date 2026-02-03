---
id: 'assignment-owned-prompt-rubric-locking-context-origin'
title: 'Assignment-owned prompt/rubric locking (context_origin)'
type: 'task'
status: 'done'
priority: 'high'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-03'
last_updated: '2026-02-03'
related: []
labels: []
---
# Assignment-owned prompt/rubric locking (context_origin)

## Objective

Make `assignment_id` mean “assignment-owned invariants” for CJ prompt building:

- `assessment_instructions` becomes the **only** source of truth for `grade_scale`,
  `student_prompt_storage_id`, and `judge_rubric_storage_id` for assignment-bound runs.
- Per-batch prompt/rubric overrides are only allowed for **guest runs** (`assignment_id=None`).
- Add an explicit DB flag (`context_origin`) to document intent and enforce RBAC/gating.
- Prevent accidental clearing of canonical storage references during instruction upserts.

## Context

ENG5 runner experiments and CJ admin tooling currently allow prompt/rubric values to drift:

- We observed real CJ dev data where `assessment_instructions.instructions_text` duplicates the
  student prompt and `judge_rubric_storage_id` was unintentionally cleared by an upsert path.
- Runner `execute` historically re-uploaded the student prompt per batch, creating new Content
  Service IDs even when the assignment configuration should be invariant.

This causes confusion (ownership unclear), makes experiments harder to reproduce, and risks
expensive CJ runs being triggered with misconfigured assignment context.

## Decisions (this slice)

- **Grade scale immutability**: once an `assessment_instructions` row exists for an `assignment_id`,
  `grade_scale` is immutable.
- **Context origin immutability**: `assessment_instructions.context_origin` is immutable once set
  (explicit intent signal; prevents accidental reclassification).
- **Assignment-bound strictness**: if a CJ request includes `assignment_id`, CJ must resolve
  `assessment_instructions` for it and treat that row as the authoritative source for prompt/rubric.
  If the row is missing, CJ rejects the request (fail-fast; avoids accidental expensive runs).
- **Rubric override gating**:
  - For **canonical** assignments (`context_origin=canonical_national`), CJ rejects any attempt to
    override `judge_rubric` at request-time.
  - For **non-canonical** assignments (e.g. `context_origin=research_experiment`), CJ allows
    request-time `LLMConfigOverrides.judge_rubric_override` so ENG5 runner can A/B test rubrics
    without mutating `assessment_instructions`.
- **Guest runs**: if `assignment_id` is omitted, per-batch prompt/rubric overrides remain allowed
  (research/experiments).

## Plan

1. CJ DB migration: add `assessment_instructions.context_origin`.
2. CJ repository hardening:
   - Fix upsert semantics so omitted storage IDs do not clear existing values.
   - Enforce `grade_scale` immutability.
3. CJ request handling:
   - When `assignment_id` is present, ignore event-level prompt/rubric refs and hydrate from
     `assessment_instructions` only.
4. ENG5 runner:
   - When `--assignment-id` is present, stop uploading student prompt at execute-time.
   - Allow optional rubric/system prompt overrides for experiments via `--rubric` / `--system-prompt`,
     but reject rubric overrides when `context_origin=canonical_national`.
5. Tests:
   - CJ unit tests for strict assignment hydration + immutability + upsert safety.
   - Runner unit tests asserting request composition changes.

## Success Criteria

- CJ rejects assignment-bound requests when `assessment_instructions` is missing (clear error).
- For assignment-bound requests, prompt/rubric used in prompt building comes only from
  `assessment_instructions`, except rubric can be overridden for non-canonical assignments.
- `assessment_instructions.grade_scale` cannot be changed after creation.
- `assessment_instructions.context_origin` cannot be changed after creation.
- Instruction upsert no longer clears `student_prompt_storage_id` / `judge_rubric_storage_id` when
  omitted from an update request.
- ENG5 runner `execute` with `--assignment-id` no longer re-uploads student prompts.
- ENG5 runner can optionally send rubric/system prompt overrides for non-canonical assignments.
- New/updated tests pass:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/`
  - `pdm run pytest-root scripts/tests/` (ENG5 runner tests relevant to request composition)

## Related

- ENG5 runner assumption hardening (R3/R4/R5): `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`
- CJ prompt contract reference: `.agent/rules/020.20-cj-llm-prompt-contract.md`
- CJ service architecture: `.agent/rules/020.7-cj-assessment-service.md`
