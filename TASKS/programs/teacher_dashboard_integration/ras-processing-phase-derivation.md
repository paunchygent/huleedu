---
id: 'ras-processing-phase-derivation'
title: 'RAS Processing Phase Derivation'
type: 'task'
status: 'blocked'
priority: 'high'
domain: 'programs'
service: 'result_aggregator_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-extended-dashboard-fields"]
labels: ["ras", "processing-phase", "internal-api"]
---
# RAS Processing Phase Derivation

## Objective

Fix `current_phase` in RAS `BatchStatusResponse` to derive from essay processing states instead of being hardcoded to `SPELLCHECK`.

## Context

The `BatchStatusResponse.current_phase` field is currently hardcoded in `from_domain()`. For the Teacher Dashboard to show accurate progress labels (e.g., "CJ-bedömning pågår", "Stavningskontroll pågår"), RAS must return the actual processing phase.

**Current behavior:**
```python
# services/result_aggregator_service/models_api.py
current_phase=ProcessingPhase.SPELLCHECK  # Hardcoded!
```

**Required behavior:**
Derive phase from essay processing states:
- If any essays have `spellcheck_status == processing` → `SPELLCHECK`
- If spellcheck done and any essays have `cj_assessment_status == processing` → `CJ_ASSESSMENT`
- If CJ done and any essays pending feedback → `FEEDBACK`
- If all done → `COMPLETED` (or None)

## Acceptance Criteria

- [ ] `BatchStatusResponse.current_phase` derives from essay states
- [ ] Phase derivation logic handles edge cases (empty batch, mixed states)
- [ ] Unit tests validate phase derivation for all scenarios
- [ ] Existing RAS tests continue to pass

## Implementation Notes

**Files to modify:**
- `services/result_aggregator_service/models_api.py` - `BatchStatusResponse.from_domain()`

**Processing phase enum:**
```python
class ProcessingPhase(str, Enum):
    UPLOAD = "upload"
    SPELLCHECK = "spellcheck"
    CJ_ASSESSMENT = "cj_assessment"
    FEEDBACK = "feedback"
    COMPLETED = "completed"
```

**Derivation logic sketch:**
```python
def derive_processing_phase(essays: list[EssayResult]) -> ProcessingPhase | None:
    if not essays:
        return None

    # Check if any essay is in spellcheck
    if any(e.spellcheck_status == "processing" for e in essays):
        return ProcessingPhase.SPELLCHECK

    # Check if any essay is in CJ assessment
    if any(e.cj_assessment_status == "processing" for e in essays):
        return ProcessingPhase.CJ_ASSESSMENT

    # Check if any essay awaits feedback
    if any(e.feedback_status == "pending" for e in essays):
        return ProcessingPhase.FEEDBACK

    # All done
    return ProcessingPhase.COMPLETED
```

## Blocked By

None - this is the first step in the live data integration chain. Status is "blocked" until prioritized for active development.

## Blocks

- `bff-extended-dashboard-fields` - BFF needs accurate phase from RAS
