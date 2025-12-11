---
type: decision
id: ADR-0023
status: accepted
created: 2025-12-08
last_updated: 2025-12-08
---

# ADR-0023: Design System Semantic Token Architecture

## Status

Accepted

## Context

The HuleEdu frontend currently uses a minimal design token system defined in
`frontend/styles/src/input.css` with only 3 core colors (canvas, navy, burgundy)
and scattered inline opacity values (e.g., `text-navy/60`, `text-navy/40`).

This approach has several problems:

1. **Accessibility failures**: Low-opacity text variants fail WCAG AA contrast
   requirements (e.g., `text-navy/60` achieves only ~3.0:1 contrast ratio)
2. **Maintenance burden**: Changing the navy color requires updating 15+ opacity
   variants scattered throughout HTML files
3. **Missing semantic layer**: No distinction between primitive colors and their
   semantic usage (text, background, border, interactive states)
4. **Incomplete system**: Missing feedback colors (success, warning), missing
   component tokens (button heights, input padding), no animation tokens

The UI design expert review identified this as a "C+ grade" system that will
create technical debt as the product scales.

## Decision

Adopt a three-tier semantic token architecture:

### Tier 1: Primitives (Raw Values)

Color scales with 50-900 shades for each brand color:

```css
--color-primitive-navy-900: #1C2E4A;
--color-primitive-navy-700: #3A5074;
--color-primitive-navy-500: #5A729E;
--color-primitive-navy-300: #9AB0D2;
--color-primitive-navy-100: #DAE8F6;
--color-primitive-navy-50: #F0F5FA;
```

### Tier 2: Semantic Tokens (Meaning)

Purpose-driven tokens that reference primitives:

```css
--color-text-primary: var(--color-primitive-navy-900);
--color-text-secondary: var(--color-primitive-navy-700);
--color-text-muted: var(--color-primitive-navy-500);
--color-bg-base: var(--color-primitive-canvas);
--color-border-default: var(--color-primitive-navy-900);
--color-interactive-primary: var(--color-primitive-burgundy-900);
```

### Tier 3: Component Tokens (Specific)

Component-level specifications:

```css
--button-height-md: 2.5rem;
--button-padding-x: 1.5rem;
--input-border-color: var(--color-border-subtle);
--input-border-color-focus: var(--color-border-strong);
```

### Typography Tokens

Semantic typography combining font, size, weight, and spacing:

```css
--type-heading-1-family: var(--font-family-serif);
--type-heading-1-size: var(--font-size-4xl);
--type-heading-1-weight: 800;
--type-heading-1-line-height: 1.1;
--type-heading-1-letter-spacing: -0.02em;
```

### Animation Tokens

Duration and easing curves:

```css
--duration-fast: 150ms;
--duration-normal: 250ms;
--ease-out: cubic-bezier(0, 0, 0.2, 1);
--transition-fast: all var(--duration-fast) var(--ease-out);
```

## Consequences

### Positive

- **Accessibility by default**: Semantic text tokens guarantee WCAG AA compliance
- **Maintainability**: Change a primitive once, propagate everywhere
- **Consistency**: Components use the same tokens, preventing drift
- **Scalability**: New components inherit existing patterns
- **Dark mode ready**: Semantic tokens can be remapped per theme

### Negative

- **Migration effort**: Existing HTML files use inline opacity values that must
  be replaced with semantic classes
- **Learning curve**: Team must understand three-tier architecture
- **Initial overhead**: More tokens to define upfront

### Risks

- Token proliferation if discipline is not maintained
- Mitigated by: validation scripts, PR review process

## Implementation

See EPIC-010 (Frontend Design System Foundational Improvements) for phased
implementation plan covering:

1. Color primitive scales
2. Semantic token layer
3. Accessibility fixes (contrast ratios, focus states)
4. Component token library
5. Animation system

## References

- `frontend/styles/src/input.css` - Current token definitions
- `frontend/docs/product/epics/design-system-epic.md` - Implementation epic
- WCAG 2.1 AA Guidelines - Contrast requirements
