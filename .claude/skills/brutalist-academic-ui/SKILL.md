---
name: brutalist-academic-ui
description: Opinionated frontend design for brutalist and academic interfaces. Grid-based layouts, systematic typography, monospace/serif pairings, high-contrast schemes. HTML, CSS, Tailwind, vanilla JS.
---

# Brutalist Academic UI

Opinionated design skill for interfaces where intellectual rigor, typographic precision, and structural honesty matter.

## When to Use

Activate when user:
- Builds websites, landing pages, dashboards, documentation sites
- Needs institutional or academic visual language
- Mentions: "brutalist", "academic", "minimal", "no gradients", "serious UI"
- Wants to avoid AI-generated aesthetic (purple gradients, Roboto, pill buttons)

## I Need To...

| Task | Read |
|------|------|
| Understand grid/typography/color principles | [fundamentals.md](fundamentals.md) |
| Build page structure, layouts, navigation | [patterns.md](patterns.md) |
| Create data tables, ledgers, state rows | [examples/tables-ledgers.md](examples/tables-ledgers.md) |
| Build buttons, cards, interactions | [examples/components.md](examples/components.md) |
| Configure Tailwind for brutalist aesthetic | [tailwind-config.md](tailwind-config.md) |

## Quick Reference

### Banned

- Purple/startup gradients
- Roboto, Open Sans, Lato, Inter
- `border-radius` > 8px
- Decorative blobs, floating shapes
- Soft shadows, backdrop blur
- Scale/bounce hover animations

### Font Stack

```css
--font-serif: 'Source Serif 4', Georgia, serif;
--font-sans: 'IBM Plex Sans', system-ui, sans-serif;
--font-mono: 'IBM Plex Mono', 'SF Mono', monospace;
```

### Spacing Scale

```css
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
--space-6: 24px;  --space-8: 32px;  --space-12: 48px; --space-16: 64px;
```

### Color Palette

```css
--color-ink: #1a1a1a;
--color-paper: #fafaf9;
--color-accent: #2563eb;
--color-error: #dc2626;
--color-success: #16a34a;
```

## Core Principle

The best interface is one where you notice the content, not the interface. Every element earns its place. Typography does the work. Whitespace is structure.
