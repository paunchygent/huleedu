---
id: ras-processing-phase-derivation
title: RAS Processing Phase Derivation
type: task
status: done
priority: high
domain: programs
service: result_aggregator_service
owner_team: agents
owner: ''
program: teacher_dashboard_integration
created: '2025-12-12'
last_updated: '2026-02-01'
related:
- TASKS/programs/teacher_dashboard_integration/HUB.md
- bff-extended-dashboard-fields
labels:
- ras
- processing-phase
- internal-api
---
# RAS Processing Phase Derivation

## Objective

Fix `current_phase` in RAS `BatchStatusResponse` to be derived from stored phase state instead of being hardcoded.

## Context

The `BatchStatusResponse.current_phase` field is currently hardcoded in `from_domain()`. For the Teacher Dashboard to show accurate progress labels (e.g., "CJ-bedömning pågår", "Stavningskontroll pågår"), RAS must return the actual processing phase.

**Current behavior:**
```python
# services/result_aggregator_service/models_api.py
current_phase=PhaseName.SPELLCHECK  # Hardcoded!
```

**Required behavior:**
Derive phase from RAS-stored phase state, with UX-safe semantics:

- `current_phase` is only meaningful while the batch is actively executing pipelines
  (`BatchStatus.PROCESSING_PIPELINES`). For READY/PENDING/terminal states, return `None`.
- Within Phase 4 scope (Spellcheck + CJ assessment), derive **the first incomplete phase**:
  - If spellcheck is incomplete for any essay → `PhaseName.SPELLCHECK`
  - Else if CJ assessment is incomplete for any essay → `PhaseName.CJ_ASSESSMENT`
  - Else → `None`

**Notes:**
- Use `ProcessingStage.terminal()` to define completion (COMPLETED/FAILED/CANCELLED). Treat `None`
  as incomplete (not yet completed).
- UX label “FEEDBACK” maps to `PhaseName.AI_FEEDBACK`, but AI feedback is explicitly **out of scope**
  for this sprint (service not yet implemented). Keep the derivation helper structured so
  `AI_FEEDBACK` can be added next sprint when RAS persists its phase status.

## Acceptance Criteria

- [x] `BatchStatusResponse.current_phase` derives from essay states (Spellcheck + CJ assessment)
- [x] Derivation gated on `BatchStatus.PROCESSING_PIPELINES`, otherwise `None`
- [x] Phase derivation logic handles edge cases (empty batch, mixed states)
- [x] Unit tests validate phase derivation for all scenarios (incl. BOS fallback metadata)
- [x] Existing RAS unit tests continue to pass

## Implementation Notes

**Files to modify:**
- `services/result_aggregator_service/models_api.py` - `BatchStatusResponse.from_domain()`
  - New helper: `BatchStatusResponse._derive_current_phase(...)`
  - Optional BOS fallback: parse `batch_metadata["current_phase"]` via `PhaseName[raw]` when essays are unavailable

**Enums to use (do not create new enums):**
- `PhaseName` in `libs/common_core/src/common_core/pipeline_models.py`
- `BatchStatus`, `ProcessingStage` in `libs/common_core/src/common_core/status_enums.py`

**Derivation logic sketch:**
```python
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, ProcessingStage

TERMINAL = ProcessingStage.terminal()

def _is_phase_incomplete(value: ProcessingStage | None) -> bool:
    return value is None or value not in TERMINAL

def derive_current_phase(batch: BatchResult) -> PhaseName | None:
    if batch.overall_status != BatchStatus.PROCESSING_PIPELINES:
        return None
    if not batch.essays:
        return None

    if any(_is_phase_incomplete(e.spellcheck_status) for e in batch.essays):
        return PhaseName.SPELLCHECK
    if any(_is_phase_incomplete(e.cj_assessment_status) for e in batch.essays):
        return PhaseName.CJ_ASSESSMENT
    return None
```

## Validation (local)

```bash
pdm run pytest-root services/result_aggregator_service/tests/unit -v
pdm run typecheck-all
pdm run format-all
pdm run lint-fix --unsafe-fixes
```

## Blocked By

None.

## Unblocks

- `bff-extended-dashboard-fields` - BFF needs accurate phase from RAS
