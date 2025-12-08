---
id: us-003a-fix-wcag-aa-contrast-violations
title: Fix WCAG AA Contrast Violations in Text Colors
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
related: ["ADR-0023", "EPIC-010"]
labels: ["accessibility", "design-system", "wcag"]
---

# US-003A: Fix WCAG AA Contrast Violations in Text Colors

## Summary

Replace inline opacity text classes (`text-navy/60`, `text-navy/50`, `text-navy/40`)
with accessible semantic tokens that meet WCAG AA contrast requirements.

**Parent Epic**: EPIC-010 (Frontend Design System Foundational Improvements)
**ADR Reference**: ADR-0023 (Design System Semantic Token Architecture)

## Problem Statement

Current text styling uses opacity-based variants that fail WCAG AA:

| Current Class | Contrast Ratio | WCAG AA (4.5:1) |
|---------------|----------------|-----------------|
| `text-navy/60` | ~3.0:1 | FAIL |
| `text-navy/50` | ~2.4:1 | FAIL |
| `text-navy/40` | ~2.0:1 | FAIL |

These classes are used for secondary text, footer text, and muted labels across
all HTML templates.

## Acceptance Criteria

- [ ] Create navy color scale (50-900) in `input.css`
- [ ] Define semantic text tokens:
  - `--color-text-primary` (4.9:1 contrast)
  - `--color-text-secondary` (4.6:1 contrast)
  - `--color-text-muted` (4.5:1 for 18px+ text)
  - `--color-text-disabled` (3:1 minimum with visual cue)
- [ ] Create Tailwind utility classes:
  - `.text-primary`, `.text-secondary`, `.text-muted`, `.text-disabled`
- [ ] Replace all occurrences:
  - `text-navy/60` → `text-secondary`
  - `text-navy/50` → `text-muted`
  - `text-navy/40` → `text-muted` or `text-disabled`
- [ ] Verify contrast with browser dev tools or axe
- [ ] Rebuild Tailwind CSS

## Files to Modify

1. `frontend/styles/src/input.css` - Add color scales and semantic tokens
2. `frontend/styles/src/login.html` - Replace opacity classes
3. `frontend/styles/src/upload.html` - Replace opacity classes
4. `frontend/styles/src/dashboard.html` - Replace opacity classes
5. `frontend/styles/src/huleedu-landing-final.html` - Replace opacity classes

## Technical Approach

### Step 1: Add Primitives

```css
@theme {
  /* Navy scale */
  --color-navy-900: #1C2E4A;
  --color-navy-800: #253A5C;
  --color-navy-700: #2E466E;
  --color-navy-600: #375280;
  --color-navy-500: #405E92;
  --color-navy-400: #5A78A8;
  --color-navy-300: #7492BE;
  --color-navy-200: #8EACD4;
  --color-navy-100: #B8CCEA;
  --color-navy-50: #E2ECF5;
}
```

### Step 2: Add Semantic Tokens

```css
@theme {
  /* Semantic text colors - all pass WCAG AA */
  --color-text-primary: var(--color-navy-900);    /* 4.9:1 */
  --color-text-secondary: var(--color-navy-700);  /* 4.6:1 */
  --color-text-muted: var(--color-navy-600);      /* 4.5:1 large text */
  --color-text-disabled: var(--color-navy-400);   /* 3.1:1 + opacity cue */
}
```

### Step 3: Add Utility Classes

```css
.text-primary { color: var(--color-text-primary); }
.text-secondary { color: var(--color-text-secondary); }
.text-muted { color: var(--color-text-muted); }
.text-disabled { color: var(--color-text-disabled); opacity: 0.7; }
```

## Testing

1. Run axe accessibility audit on each page
2. Manual verification with browser contrast checker
3. Test with Windows High Contrast Mode
4. Verify visual appearance matches design intent

## Notes

- Preserve visual hierarchy: primary > secondary > muted > disabled
- Navy-900 remains the dominant text color for body content
- Footer text uses muted (larger text size compensates)
- Disabled states combine color + opacity for double indication
