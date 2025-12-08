---
id: 201-tailwind-4
type: standards
created: '2025-12-08'
last_updated: '2025-12-08'
scope: frontend
---

# Tailwind CSS v4 Quickstart

This project tracks Tailwind CSS v4 (stable line currently at the 4.1.x series). Use these conventions when wiring new templates or CLI features.

## Installation
```bash
pnpm add -D tailwindcss @tailwindcss/cli
```
The v4 toolchain bundles Lightning CSS, autoprefixer, and `@import` handling, so no extra PostCSS plugins are required unless you need bundler-specific integrations. Allow pnpm to manage versions via caret ranges; avoid manual pins unless a regression forces a temporary lock.

## Base CSS Entry Point
Create `styles/src/tailwind.css` with the new CSS-first configuration style:
```css
@import "tailwindcss";

@theme {
  --font-family-sans: "Inter", system-ui, sans-serif;
  --color-brand-primary: oklch(65% 0.2 257);
  --radius-card: 18px;
}
```
- `@import "tailwindcss";` replaces the old `@tailwind` directives.
- Use `@theme` to expose custom theme tokens as CSS variables (acts like `theme.extend`).
- Use CSS custom properties (exposed by `@theme`) inside arbitrary values such as `bg-[var(--color-brand-primary)]`.

## CLI Usage
The bundled CLI handles builds and watch mode with zero extra config:
```bash
# One-off build
pnpm run tailwind:build

# Watch mode
pnpm run tailwind:watch
```
The CLI automatically discovers template files using heuristics informed by `.gitignore`. If you need explicit control later, keep custom globs inside a `tailwind.config.cjs` or pass them with `--content` once the feature ships for v4 GA.

## Key Changes vs v3
- **New engine written with Rust components** — builds are up to 10× faster and ship with a smaller dependency footprint (Lightning CSS is the only runtime dependency).
- **Unified toolchain** — vendor prefixes, nesting, and syntax transforms (e.g. `oklch()` or range media queries) are included by default; drop `postcss`/`autoprefixer` from project dependencies.
- **Composable variants** — variants such as `group-*`, `peer-*`, `has-*`, and the new `not-*` stack arbitrarily (`group-not-has-peer-focus:underline`).
- **Zero-config content detection** — Tailwind crawls the project (or leverages the Vite module graph) to discover templates without manual `content` arrays.
- **CSS-first authoring** — theme values are surfaced as native CSS variables so arbitrary values and integration with JS animation libraries no longer need `theme()` lookups.

## Migration Tips
1. Delete legacy `tailwind.config.js` content arrays unless you depend on custom paths; document overrides once v4 exposes configuration hooks.
2. Replace `@tailwind base; @tailwind components; @tailwind utilities;` with a single `@import "tailwindcss";` line.
3. Move existing palette/spacing tokens to `@theme` blocks so new CSS variables mirror design tokens.
4. Update project scripts (`pnpm run tailwind:build`) to point at `styles/src/tailwind.css` and emit to `styles/dist/tailwind.css`.
5. If you ship storybooks or previews, run the CLI in watch mode instead of relying on a Vite dev server unless hot reloading is mandatory.

## Resources
- Tailwind Labs announcement: [Tailwind CSS v4 Alpha](https://tailwindcss.com/blog/tailwindcss-v4-alpha) (retrieved 2025-10-01).
- Default theme variables: [tailwindlabs/tailwindcss `next` branch](https://github.com/tailwindlabs/tailwindcss/tree/next/packages/tailwindcss/src/public/defaultTheme.ts).
