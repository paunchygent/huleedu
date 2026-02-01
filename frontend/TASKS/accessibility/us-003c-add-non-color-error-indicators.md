---
id: us-003c-add-non-color-error-indicators
title: Add Non-Color Error Indicators for WCAG 1.4.1 Compliance
type: story
status: proposed
priority: medium
domain: accessibility
service: ''
owner_team: agents
owner: ''
program: ''
created: 2025-12-08
last_updated: '2026-02-01'
related:
- ADR-0023
- EPIC-010
- us-003a-fix-wcag-aa-contrast-violations
labels:
- accessibility
- design-system
- wcag
---

# US-003C: Add Non-Color Error Indicators for WCAG 1.4.1 Compliance

## Summary

Ensure error and status states are indicated by more than color alone,
supporting users with color vision deficiencies.

**Parent Epic**: EPIC-010 (Frontend Design System Foundational Improvements)
**WCAG Reference**: 1.4.1 Use of Color (Level A)

## Problem Statement

Current UI uses color as the sole indicator for:

| Element | Current Indicator | Issue |
|---------|-------------------|-------|
| Spelling errors (`.wavy-error`) | Red wavy underline | Color only |
| Status dots | Red/amber/green circles | Color only, same shape |
| Form validation | Red border | Color only |

Users with color blindness cannot distinguish these states.

## Acceptance Criteria

- [ ] Spelling errors include icon or pattern alongside color
- [ ] Status dots use different shapes per status:
  - Error: diamond shape
  - Warning: triangle shape
  - Success: circle (checkmark inside)
  - Info: square
- [ ] Form validation errors include icon and text label
- [ ] All error indicators work in grayscale view
- [ ] Test with color blindness simulation (Daltonize or similar)

## Files to Modify

1. `frontend/styles/src/input.css` - Status dot shapes, error patterns
2. `frontend/styles/src/dashboard.html` - Update status dot markup
3. `frontend/styles/src/upload.html` - Update validation error display

## Technical Approach

### Status Dots with Shapes

```css
/* Base status dot */
.status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
}

/* Error - diamond shape */
.status-dot--error {
  background: var(--color-burgundy);
  clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
}

/* Warning - triangle shape */
.status-dot--warning {
  background: var(--color-amber-500);
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
}

/* Success - circle with checkmark or just circle */
.status-dot--success {
  background: var(--color-green-600);
  border-radius: 50%;
}

/* Info - square */
.status-dot--info {
  background: var(--color-navy-600);
  border-radius: 0;
}
```

### Spelling Error Enhancement

```css
/* Add icon before error text */
.wavy-error {
  text-decoration: underline wavy var(--color-burgundy);
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
  position: relative;
}

/* Optional: prefix with warning indicator */
.wavy-error::before {
  content: "⚠ ";
  font-size: 0.8em;
  color: var(--color-burgundy);
}
```

### Form Validation

```html
<!-- Error state with icon + text -->
<div class="input-error">
  <svg class="error-icon" aria-hidden="true"><!-- exclamation icon --></svg>
  <span class="error-text">This field is required</span>
</div>
```

```css
.input-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-burgundy);
  font-size: var(--font-size-sm);
}

.error-icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}
```

## Testing

1. **Grayscale Test**
   - View pages in grayscale mode
   - Verify all statuses distinguishable by shape

2. **Color Blindness Simulation**
   - Use browser extension (e.g., NoCoffee)
   - Test protanopia, deuteranopia, tritanopia modes
   - Verify status indicators remain distinguishable

3. **Screen Reader**
   - Verify status is announced (not just visual)
   - Ensure error messages are associated with inputs via aria-describedby

## Notes

- clip-path has good browser support (95%+ global)
- Consider adding sr-only text for status dots: "Status: Error"
- Coordinate with EPIC to define complete feedback color palette
- Icons should use aria-hidden="true" when decorative
