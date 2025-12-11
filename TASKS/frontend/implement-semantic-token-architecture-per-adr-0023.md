---
id: 'implement-semantic-token-architecture-per-adr-0023'
title: 'Implement semantic token architecture per ADR-0023'
type: 'task'
status: 'research'
priority: 'high'
domain: 'frontend'
service: ''
owner_team: 'agents'
owner: ''
program: 'EPIC-010'
created: '2025-12-11'
last_updated: '2025-12-11'
related: ['frontend/docs/decisions/0023-design-system-semantic-token-architecture.md', 'frontend/docs/product/epics/design-system-epic.md']
labels: ['accessibility', 'design-system']
---
# Implement semantic token architecture per ADR-0023

## Objective

Replace inline opacity color values (`text-navy/60`, `text-navy/40`) with semantic tokens that guarantee WCAG AA contrast compliance and improve maintainability.

## Context

Current implementation uses Tailwind opacity modifiers scattered across Vue components:
- `text-navy/70` for secondary text
- `text-navy/60` for muted text (fails WCAG AA at ~3.0:1 contrast)
- `text-navy/40` for disabled/archived states
- `text-navy/30` for very faded elements

This approach:
1. Fails accessibility requirements
2. Is hard to maintain (15+ usages across components)
3. Has no semantic meaning (what does `/40` mean?)

ADR-0023 defines a three-tier architecture: Primitives → Semantic → Component tokens.

## Plan

### Phase 1: Add primitive color scales (non-breaking)
1. Define navy scale (50-900) in `main.css` @theme block
2. Define burgundy scale (50-900)
3. Ensure primitives pass contrast requirements

### Phase 2: Add semantic tokens
1. Define `--color-text-primary` (navy-900, 4.9:1)
2. Define `--color-text-secondary` (navy-700, 4.5:1)
3. Define `--color-text-muted` (navy-500, 4.5:1 large text)
4. Define `--color-text-disabled` (navy-400)

### Phase 3: Replace inline opacity values
Files to update:
- `frontend/src/components/dashboard/LedgerRow.vue`
- `frontend/src/components/dashboard/ActionCard.vue`
- `frontend/src/components/dashboard/SectionHeader.vue`
- `frontend/src/views/TeacherDashboardView.vue`
- `frontend/src/views/LoginView.vue`
- `frontend/src/components/layout/AppHeader.vue`
- `frontend/src/components/layout/AppSidebar.vue`

### Phase 4: Verify and document
1. Run contrast checker on all text colors
2. Update design-spec-teacher-dashboard.md Section 7.1
3. Remove "Planned" label from documentation

## Success Criteria

- [ ] Zero inline opacity color values remain in Vue components
- [ ] All text colors achieve WCAG AA contrast (4.5:1 normal, 3:1 large)
- [ ] Semantic tokens defined in `main.css` @theme block
- [ ] Tailwind utilities generated for all tokens
- [ ] Documentation updated

## Related

- [ADR-0023](../../frontend/docs/decisions/0023-design-system-semantic-token-architecture.md)
- [EPIC-010](../../frontend/docs/product/epics/design-system-epic.md)
- [Design Spec Section 7.1](../../frontend/docs/product/epics/design-spec-teacher-dashboard.md)
