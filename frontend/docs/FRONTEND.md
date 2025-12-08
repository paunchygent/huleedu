# Frontend Development Guidelines

> **Philosophy:** Purist, fast, semantic. Every dependency must justify its weight.

## Technology Stack

| Priority | Technology | Use Case |
|----------|------------|----------|
| 1 | HTML + Tailwind CSS | All pages by default |
| 2 | Vanilla JavaScript | Simple interactivity (dropdowns, toggles, validation) |
| 3 | Vue + Vite | Only when truly necessary |

## Typography

**IBM Plex** industrial type system:
- `IBM Plex Sans` – Body text, UI elements
- `IBM Plex Serif` – Accent text, quotes, emphasis

```html
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;600&display=swap" rel="stylesheet">
```

## Performance Rules

### Do
- **Inline critical CSS** in `<head>` for above-the-fold content
- **Defer non-essential JS** with `defer` or `async`
- **Use CSS transitions** (max 150ms) instead of JS animations
- **Lazy load images** below the fold
- **Minify everything** for production

### Don't
- Add animations for decoration
- Import entire libraries for single features
- Use JS when CSS can do the job
- Add npm packages without justification

## Animation Policy

**Default: No animations.**

Exceptions (where motion provides critical UX value):
- Loading/processing states (spinner, progress bar)
- Error feedback (shake, highlight)
- State transitions users must notice (expand/collapse)
- Focus indicators for accessibility

When animation is justified:
```css
/* Use CSS transitions, not JS */
.element {
    transition: opacity 150ms ease-out;
}
```

## When Vue + Vite is Justified

Use Vue only for:
1. **Complex forms** – Real-time validation, conditional fields
2. **Dynamic data tables** – Sorting, filtering, pagination
3. **Multi-step wizards** – State that spans multiple views
4. **Real-time updates** – WebSocket/SSE integration
5. **Reusable component libraries** – Shared across multiple pages

For everything else: HTML + Tailwind + Vanilla JS.

## File Structure

```
styles/
├── src/
│   ├── input.css          # Tailwind source
│   ├── tailwind.css        # Compiled output (gitignored)
│   ├── *.html              # Static pages
│   └── *.js                # Vanilla JS modules
└── icons_favicons/         # SVG assets
```

## Build Commands

```bash
# Development (watch mode)
pnpm tailwind:watch

# Production build
pnpm tailwind:build
```

## Checklist Before Adding Dependencies

- [ ] Can this be done with HTML/CSS alone?
- [ ] Can this be done with Vanilla JS (<50 lines)?
- [ ] Is this a one-time use or repeated pattern?
- [ ] What's the bundle size impact?
- [ ] Is there a lighter alternative?

---

*Last updated: December 2024*
