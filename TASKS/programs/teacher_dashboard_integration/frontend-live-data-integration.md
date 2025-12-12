---
id: 'frontend-live-data-integration'
title: 'Frontend Live Data Integration'
type: 'task'
status: 'blocked'
priority: 'high'
domain: 'programs'
service: 'frontend'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-extended-dashboard-fields", "websocket-batch-updates", "entitlements-credits-endpoint"]
labels: ["frontend", "vue", "pinia", "live-data"]
---
# Frontend Live Data Integration

## Objective

Wire frontend Pinia dashboard store to real BFF API, removing mock data and enabling live batch display.

## Context

This is the **final step** in the inside-out integration. All backend work must be complete:
- RAS exposes accurate `current_phase`
- BFF exposes extended fields (`failed_essays`, `completed_at`, `processing_phase`)
- CMS validation endpoint provides `deviation_count`, `auto_confirm_deadline`
- WebSocket pushes real-time updates
- Credits endpoint available

Only then should frontend switch to live data.

## Acceptance Criteria

- [ ] Mock data removed from `useDashboardStore`
- [ ] Real API call via `fetchTeacherDashboard()`
- [ ] Batch mapper transforms API response to store model
- [ ] Swedish status labels per UX spec
- [ ] Time display logic (relative dates)
- [ ] WebSocket composable for real-time updates
- [ ] Credits display (or hide if not available)
- [ ] Error handling with Swedish messages
- [ ] Type-check and lint pass

## Implementation Notes

**Files to create/modify:**
- `frontend/src/utils/batch-mapper.ts` - NEW
- `frontend/src/stores/dashboard.ts` - MODIFY
- `frontend/src/schemas/teacher-dashboard.ts` - MODIFY (add new fields)
- `frontend/src/composables/useWebSocket.ts` - NEW (if WebSocket ready)

**Batch mapper:**
```typescript
export function mapBatchItemToDashboard(item: TeacherBatchItem): DashboardBatch {
  const state = deriveState(item.status);
  return {
    id: item.batch_id,
    batchCode: deriveBatchCode(item.batch_id),
    title: item.title,
    className: item.class_name,
    state,
    status: item.status,
    statusLabel: STATUS_CONFIG[item.status].label,
    // ... full mapping
  };
}
```

**Swedish status labels:**

| Status | statusLabel | progressLabel |
|--------|-------------|---------------|
| `pending_content` | "Inväntar innehåll" | null |
| `ready` | "Redo" | "Klicka för att starta" |
| `processing` (spellcheck) | "Bearbetar" | "Stavningskontroll pågår" |
| `processing` (cj_assessment) | "Bearbetar" | "CJ-bedömning pågår" |
| `processing` (feedback) | "Bearbetar" | "Genererar feedback" |
| `completed_successfully` | "Klar" | "Redo för granskning" |
| `completed_with_failures` | "Klar" | "{n} avvikelser" |
| `failed` | "Misslyckades" | null |
| `cancelled` | "Avbruten" | null |

**Time display:**
- Processing: empty
- Completed today: "14:32"
- Yesterday: "Igår"
- This week: "Måndag"
- Older: "3 dec"

**Error messages (Swedish):**
- 500+: "Serverfel. Försök igen senare."
- 401: "Du är utloggad. Logga in igen."
- 403: "Du har inte behörighet."
- Network: "Kunde inte ansluta till servern."
- Zod: "Oväntat dataformat från servern."

## Blocked By

- `ras-processing-phase-derivation` - Phase 1
- `bff-extended-dashboard-fields` - Phase 2
- `cms-student-validation-endpoint` - Phase 3
- `bff-cms-validation-integration` - Phase 3
- `websocket-batch-updates` - Phase 4
- `entitlements-credits-endpoint` - Phase 5

**All above must be complete before starting this task.**

## Blocks

None - this is the final step.
