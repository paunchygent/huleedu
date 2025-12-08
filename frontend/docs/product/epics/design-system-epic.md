---
type: epic
id: EPIC-010
title: Frontend Design System Foundational Improvements
status: draft
phase: 1
sprint_target: 2025-W50
created: 2025-12-08
last_updated: 2025-12-08
---

# EPIC-010: Frontend Design System Foundational Improvements

## Summary

Establish a production-grade design system with semantic token architecture,
WCAG AA accessibility compliance, and systematic component patterns. This
addresses technical debt identified in UI design review (grade C+) before
scaling the frontend.

**Business Value**: Reduces maintenance cost, ensures accessibility compliance,
enables consistent UI development velocity.

**Scope Boundaries**:

- **In Scope**: Token architecture, accessibility fixes, component tokens, animation system
- **Out of Scope**: New feature development, major visual redesign, dark mode implementation

## User Stories

### US-003.1: Color Primitive Scale

**As a** frontend developer
**I want** a complete color scale (50-900) for each brand color
**So that** I don't use inline opacity hacks that break accessibility.

**Acceptance Criteria**:

- [ ] Navy scale: 50, 100, 200, 300, 400, 500, 600, 700, 800, 900
- [ ] Burgundy scale: 50, 100, 200, 300, 400, 500, 600, 700, 800, 900
- [ ] Canvas variations for elevated surfaces
- [ ] All scales defined in `input.css` @theme block
- [ ] Tailwind utilities generated for all primitives

### US-003.2: Semantic Text Colors

**As a** frontend developer
**I want** semantic text color tokens (primary, secondary, muted, disabled)
**So that** all text automatically meets WCAG AA contrast requirements.

**Acceptance Criteria**:

- [ ] `--color-text-primary` achieves 4.9:1 contrast on canvas
- [ ] `--color-text-secondary` achieves 4.5:1 contrast on canvas
- [ ] `--color-text-muted` achieves 4.5:1 for large text (18px+)
- [ ] `--color-text-disabled` clearly indicates disabled state
- [ ] Replace all `text-navy/60`, `text-navy/50`, `text-navy/40` usages

### US-003.3: Focus State Completeness

**As a** keyboard user
**I want** visible focus indicators on all interactive elements
**So that** I can navigate the interface without a mouse.

**Acceptance Criteria**:

- [ ] Custom radio buttons (`.batch-mode-option`) have focus ring
- [ ] Interactive table rows (`.ledger-row`) have focus indicator
- [ ] Upload drop zone has visible focus state
- [ ] All focus states use consistent 2px burgundy outline
- [ ] Focus states tested with keyboard-only navigation

### US-003.4: Non-Color Error Indicators

**As a** color-blind user
**I want** error states indicated by more than color alone
**So that** I can identify errors without relying on red/green distinction.

**Acceptance Criteria**:

- [ ] Spelling errors (`.wavy-error`) include icon or shape indicator
- [ ] Status dots use different shapes (circle, triangle, diamond)
- [ ] Error messages include warning icon
- [ ] WCAG 1.4.1 Use of Color compliance verified

### US-003.5: Component Token Library

**As a** frontend developer
**I want** standardized component tokens (button, input, card)
**So that** components are consistent without custom CSS overrides.

**Acceptance Criteria**:

- [ ] Button tokens: height (sm/md/lg), padding, border-radius, font-size
- [ ] Input tokens: height, padding, border-color states, focus ring
- [ ] Card tokens: padding, border, shadow, radius
- [ ] All tokens documented in design system reference

### US-003.6: Animation/Motion Tokens

**As a** frontend developer
**I want** standardized duration and easing tokens
**So that** animations feel consistent and respect user preferences.

**Acceptance Criteria**:

- [ ] Duration tokens: fast (150ms), normal (250ms), slow (400ms)
- [ ] Easing tokens: ease-out, ease-in-out, bounce
- [ ] Transition presets: `--transition-fast`, `--transition-normal`
- [ ] `prefers-reduced-motion` media query respected
- [ ] Applied to existing hover/focus transitions

## Technical Architecture

### Token File Structure

```
frontend/styles/src/
├── input.css              # Main entry, imports tokens
├── tokens/
│   ├── primitives.css     # Color scales, spacing base
│   ├── semantic.css       # Text, background, border tokens
│   ├── components.css     # Button, input, card tokens
│   └── animation.css      # Duration, easing tokens
```

### Migration Strategy

1. **Phase 1**: Add primitive scales alongside existing colors (non-breaking)
2. **Phase 2**: Add semantic tokens referencing primitives
3. **Phase 3**: Replace inline opacity values with semantic classes
4. **Phase 4**: Add component tokens for buttons, inputs, cards
5. **Phase 5**: Add animation tokens and apply to transitions

### Files to Modify

- `frontend/styles/src/input.css` - Token definitions
- `frontend/styles/src/login.html` - Replace inline opacity classes
- `frontend/styles/src/upload.html` - Replace inline opacity classes
- `frontend/styles/src/dashboard.html` - Replace inline opacity classes
- `frontend/styles/src/huleedu-landing-final.html` - Replace inline opacity classes

## Dependencies

- ADR-0023: Design System Semantic Token Architecture (accepted)
- Tailwind CSS v4.1.14 @theme support
- No backend dependencies

## Acceptance Criteria (Epic-Level)

- [ ] All WCAG AA contrast violations fixed
- [ ] All interactive elements have visible focus states
- [ ] Zero inline opacity color values remain in HTML
- [ ] Component token library documented
- [ ] Animation system documented
- [ ] Tailwind CSS rebuilt with new tokens
- [ ] Visual regression testing passed

## Notes

- IBM Plex font system is retained (excellent choice for educational context)
- Brutalist aesthetic preserved; tokens enable consistency, not redesign
- Dark mode implementation deferred to future epic
- This is foundational work enabling future frontend scaling
