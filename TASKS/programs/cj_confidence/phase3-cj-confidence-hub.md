---
id: "phase3-cj-confidence-hub"
title: "Phase 3 – CJ Confidence Programme Hub"
type: "programme"
status: "research"
priority: "medium"
domain: "programs"
service: ""
owner_team: "agents"
owner: ""
program: "cj_confidence"
created: "2025-11-09"
last_updated: "2025-11-17"
related: []
labels: []
---
**Purpose**: Provide a single overview for Phase 3 workstreams so contributors can see status, owners, and next actions without traversing multiple task files.

## 1. Programme Snapshot

| Workstream | Task File | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| Mathematical Validation | `TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md` | TBD | 🔄 In Progress | Phases 1–2 complete, Phase 3 empirical validation pending |
| Grade Scale Enablement & Data Capture | `TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md` | TBD | 🔄 In Progress | Phase 3.1–3.2 done, Phase 3.3 artefact capture outstanding |
| Prompt Architecture Implementation | `TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md` | TBD | 🔄 In Progress | Prompt references rolled out; downstream fixtures/docs aligning |
| Architect Working Session | `TASK-CJ-PHASE3-ARCHITECT-NEXT-SESSION.md` | Lead Architect Agent | ⏳ Scheduled | Next session to finalize runner validation + ops guidance |

_Last refresh: 2025-11-09_

## 2. Active Workstreams

1. **Mathematical Validation** (`TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`)
   - Focus: empirical SE vs confidence calibration, framework comparison, recommendations.
   - Immediate next steps: ingest Session 1/2 data, bootstrap analysis, implement validation scripts.

2. **Grade Scale Enablement & Data Capture** (`TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`)
   - Focus: confirm Phase 3.2 validation, execute ENG5 batch capture, archive artefacts per schema.
   - Next checkpoints: ENG5 scale tests, runner dry-run + execute, documentation updates.

3. **Prompt Architecture Implementation** (`TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md`)
   - Focus: downstream consumer alignment, Result Aggregator fixture updates, observability verification.
   - Next steps: coordinate BI/dashboard changes, expand tests/metrics coverage.

4. **Architect Session Prep** (`TASK-CJ-PHASE3-ARCHITECT-NEXT-SESSION.md`)
   - Focus: ENG5 runner execute-mode readiness, schema validation, operational playbook updates.
   - Upcoming agenda: finalize runner validation tests, document execute-mode checklist, confirm monitoring strategy.

## 3. Key Artefacts & Commands

- **Runner package**: `scripts/cj_experiments_runners/eng5_np/`
- **JSON schema**: `Documentation/schemas/eng5_np/assessment_run.schema.json`
- **Primary tests**:
  - `pdm run pytest-root scripts/tests/test_eng5_np_runner.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_routes.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_cli.py`
- **Observability**:
  - Metrics: `huleedu_{nlp|cj}_prompt_fetch_failures_total`, `cj_admin_instruction_operations_total`, `huleedu_bcs_prompt_prerequisite_blocked_total`
  - Dashboards: see `Documentation/OPERATIONS/01-Grafana-Playbook.md`

## 4. Decisions & Risks

| Date | Decision | Source |
| --- | --- | --- |
| 2025-11-08 | Runner relies on Kafka callbacks + JSON artefact hydration (no direct DB reads) | `TASK-CJ-PHASE3-ARCHITECT-NEXT-SESSION.md` |
| 2025-11-06 | Prompt references replace essay_instructions across services | `TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.md` |

**Current risks**

- Legacy fixtures still referencing `essay_instructions` → coordinate cleanup (prompt architecture task).
- Downstream BI/AI Feedback not yet consuming `student_prompt_ref` → track in prompt architecture task.

## 5. Upcoming Milestones

| Target Date | Milestone | Blocking Items |
| --- | --- | --- |
| 2025-11-12 | ENG5 runner dry-run + execute artefacts | Prompt architecture tests; admin CLI validation |
| 2025-11-15 | Phase 3 empirical dataset ready | Runner execute artefacts; prompt architecture fixture updates |
| 2025-11-20 | Confidence recommendation draft | Empirical validation scripts; literature comparison matrix |

## 6. Change Log

- **2025-11-09** – Hub created; initial status populated from task progress logs.
