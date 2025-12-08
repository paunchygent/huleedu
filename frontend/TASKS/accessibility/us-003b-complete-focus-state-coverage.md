---
id: us-003b-complete-focus-state-coverage
title: Complete Focus State Coverage for All Interactive Elements
type: story
status: research
priority: high
domain: accessibility
service: ''
owner_team: agents
owner: ''
program: ''
created: 2025-12-08
last_updated: 2025-12-08
related: ["ADR-0023", "EPIC-010", "us-003a-fix-wcag-aa-contrast-violations"]
labels: ["accessibility", "design-system", "keyboard-navigation"]
---

# US-003B: Complete Focus State Coverage for All Interactive Elements

## Summary

Add visible focus indicators to all interactive elements that currently lack
them, ensuring keyboard-only users can navigate the interface.

**Parent Epic**: EPIC-010 (Frontend Design System Foundational Improvements)

## Problem Statement

Current focus state coverage is incomplete:

| Element | Focus State |
|---------|-------------|
| `<a>`, `<button>`, `<input>`, `<select>` | Present (2px burgundy outline) |
| Custom radio buttons (`.batch-mode-option`) | MISSING |
| Interactive table rows (`.ledger-row`) | MISSING |
| Upload drop zone (`#drop-zone`) | MISSING |
| Login cells (`.login-cell`) | MISSING |

Users navigating with keyboard cannot see which element is focused for these
custom components.

## Acceptance Criteria

- [ ] Custom radio buttons show focus ring when child input is focused
- [ ] Interactive ledger rows show focus indicator on focus-within
- [ ] Upload drop zone shows focus ring when tabbed to
- [ ] Login cells show focus state distinct from hover
- [ ] All focus indicators use consistent styling:
  - 2px solid burgundy outline
  - 2px offset
- [ ] Test with keyboard-only navigation (Tab, Shift+Tab, Enter, Space)
- [ ] Test with screen reader (VoiceOver on macOS)

## Files to Modify

1. `frontend/styles/src/input.css` - Add focus state rules
2. `frontend/styles/src/upload.html` - Verify drop zone tabindex
3. `frontend/styles/src/dashboard.html` - Verify interactive rows

## Technical Approach

### Add to input.css

```css
/* Custom radio buttons - focus on parent when input focused */
.batch-mode-option:has(:focus-visible) {
  outline: 2px solid var(--color-burgundy);
  outline-offset: 2px;
}

/* Interactive ledger rows - focus-within for row focus */
.ledger-row:focus-within {
  outline: 2px solid var(--color-burgundy);
  outline-offset: -2px;  /* Inset to avoid layout shift */
}

/* Upload drop zone */
#drop-zone:focus-visible {
  outline: 2px solid var(--color-burgundy);
  outline-offset: 4px;  /* Extra offset due to padding */
}

/* Login cells - distinguish focus from hover */
.login-cell:focus-visible {
  outline: 2px solid var(--color-burgundy);
  outline-offset: 2px;
}

/* Ensure all interactive elements with tabindex have focus */
[tabindex="0"]:focus-visible {
  outline: 2px solid var(--color-burgundy);
  outline-offset: 2px;
}
```

### Verify HTML Attributes

Ensure interactive elements have proper attributes:

```html
<!-- Drop zone must be focusable -->
<div id="drop-zone" tabindex="0" role="button" aria-label="Upload files">

<!-- Ledger rows with interactions need tabindex -->
<tr class="ledger-row" tabindex="0" role="row">
```

## Testing Checklist

1. **Tab Navigation**
   - [ ] Can tab through all form elements
   - [ ] Can tab to drop zone
   - [ ] Can tab through ledger rows
   - [ ] Focus order matches visual order

2. **Focus Visibility**
   - [ ] Focus ring visible on all focusable elements
   - [ ] Focus ring has sufficient contrast (burgundy on canvas)
   - [ ] Focus ring doesn't cause layout shift

3. **Screen Reader**
   - [ ] VoiceOver announces all focusable elements
   - [ ] Role and label announced correctly
   - [ ] State changes announced (expanded, selected)

## Notes

- `:focus-visible` used instead of `:focus` to avoid focus ring on mouse click
- `:has()` selector requires modern browser (Safari 15.4+, Chrome 105+)
- Fallback for older browsers: use `:focus-within` on parent containers
- Coordinate with US-003A to ensure focus ring color has sufficient contrast
