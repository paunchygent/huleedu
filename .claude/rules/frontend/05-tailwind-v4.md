# Tailwind v4 Quirks

## Hover States

Tailwind v4 uses CSS nesting (`&:hover`) which has incomplete browser support.

**Fix in `main.css`:**
```css
@import "tailwindcss";
@custom-variant hover (&:hover);
```

For buttons, add explicit CSS rules (lines 306-328 in main.css) instead of relying on Tailwind hover utilities.

## Grid + Border

Never put `border-l-*` on a grid row div - it shifts all columns. Apply to the first cell instead.
