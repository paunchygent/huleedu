# Tailwind v4 Patterns

## Hover States Philosophy

Tailwind v4 wraps hover states in `@media (hover: hover)` by default. This means:
- **Pointer devices** (mouse, trackpad): Hover effects work normally
- **Touch devices**: Hover effects are disabled to avoid "sticky" states

**We align with this philosophy.** Treat hover as an enhancement, not a requirement.

### Button States Pattern

```css
/* Active states - touch feedback for ALL devices */
button.bg-burgundy:active { background-color: var(--color-navy); }

/* Hover states - only for pointer devices */
@media (hover: hover) {
  button.bg-burgundy:hover { background-color: var(--color-navy); }
}
```

### What NOT to do

Do NOT override Tailwind's default hover behavior:
```css
/* WRONG - forces hover on touch devices, causes sticky states */
@custom-variant hover (&:hover);
```

### Implementation in main.css

- Lines 110-125: Ledger/batch row hovers wrapped in `@media (hover: hover)`
- Lines 248-264: Ledger row system hovers wrapped in `@media (hover: hover)`
- Lines 310-325: Button `:active` states for touch feedback
- Lines 327-344: Button `:hover` states in `@media (hover: hover)`

## Grid + Border

Never put `border-l-*` on a grid row div - it shifts all columns. Apply to the first cell instead.

## Mobile-First

Always design mobile-first:
- Base styles work without hover
- Use breakpoint prefixes (`md:`, `lg:`) to add complexity
- `sm:` means "at small breakpoint and up", not "on small screens"
