# Brutalist Academic UI Fundamentals

**Responsibility**: Core convictions and WHY decisions.

---

## 1. The Grid Is Sacred

The grid is the skeleton. Not a suggestion.

- Use CSS Grid. Not flexbox-for-everything.
- Baseline grid: 8px (or 4px for precision)
- Columns with purpose. 12-column means nothing if you only use 1 and 11.
- Gutters: 24px, 32px, or 48px. Pick one.
- If something is 3px off, fix it.

```css
.layout {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 32px;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 48px;
}
```

---

## 2. Typography Is The Interface

Type does 80% of the work. The interface is a reading environment.

### Font Stack

| Purpose | Fonts | Never |
|---------|-------|-------|
| Body | Georgia, Charter, Source Serif, IBM Plex Sans | Roboto, Open Sans, Lato, Inter |
| Headings | Same as body, or contrasting sans | Decorative display fonts |
| Monospace | JetBrains Mono, Berkeley Mono, IBM Plex Mono | System defaults |

### Measure (Line Length)

45-75 characters. Not optional.

```css
.prose { max-width: 65ch; }
```

---

## 3. Color Is Information

Color has semantic meaning or it doesn't exist.

### Banned

- Purple gradients (Stripe/Linear is dead)
- Gradients in general (unless specific reason)
- Background colors for "visual interest"
- Colored shadows
- Opacity below 0.1 for "subtle effect"

---

## 4. Borders, Not Shadows

Brutalist = hard edges. Academic = clear delineation.

```css
/* Yes */
.card { border: 1px solid var(--color-gray-200); }
.card { border: 2px solid var(--color-ink); }

/* Acceptable for elevation */
.card-elevated { box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }

/* Banned */
.card-slop {
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(139, 92, 246, 0.25);
  backdrop-filter: blur(10px);
}
```

### Border Radius

- 0px: valid, often correct
- 2-4px: subtle softening
- 8px max: cards/containers
- Never: 16px, 24px, 9999px pill shapes

---

## 5. Whitespace Is Structure

Whitespace is architecture, not empty space.

- Follow baseline grid for margins/padding
- Generous whitespace = confidence
- Cramped layouts = uncertainty
- Section spacing > element spacing

---

## 6. No Decoration Without Function

Every visual element must do something.

### Banned

- Floating shapes for "visual interest"
- Gradient blobs
- Decorative SVG patterns
- Parallax for parallax's sake
- Animations that don't communicate state
- "Fun" hover effects

### Allowed

- Borders that delineate sections
- Horizontal rules that separate content
- Icons that convey meaning
- State transitions (hover = interactive)
- Loading states that communicate progress

---

## 7. Interactions Are Honest

Hover states communicate "this is interactive."

No bounces. No 3D transforms. No `scale(1.05)`. The user clicked a button, not launched a rocket.

---

## Success Criteria

A successful brutalist/academic interface:

1. Can be understood with CSS disabled
2. Looks intentional, not default
3. Communicates hierarchy through typography alone
4. Has no element you cannot justify
5. Loads fast (not drowning in assets)
6. Works in print (cmd+P produces something readable)
7. Respects user's time and attention
