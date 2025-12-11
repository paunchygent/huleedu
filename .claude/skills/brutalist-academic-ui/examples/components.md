# Components

**Responsibility**: Reusable UI elements. Copy-paste ready.

---

## 1. Hard Shadow Button

Brutalist signature: offset shadow with translate-on-press.

```css
.btn-brutal {
  background: var(--color-ink);
  color: white;
  padding: var(--space-3) var(--space-6);
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: none;
  cursor: pointer;
  box-shadow: 4px 4px 0 0 var(--color-ink);
  transition: transform 0.075s ease, box-shadow 0.075s ease;
}

.btn-brutal:hover {
  background: var(--color-gray-800);
}

.btn-brutal:active {
  transform: translate(4px, 4px);
  box-shadow: none;
}

/* Accent variant */
.btn-brutal-accent {
  background: var(--color-accent);
  box-shadow: 4px 4px 0 0 var(--color-ink);
}
```

---

## 2. Cards

```css
/* Primary: hard border, hard shadow */
.card-brutal {
  background: white;
  border: 2px solid var(--color-ink);
  box-shadow: 8px 8px 0 0 var(--color-ink);
}

/* Secondary: softer shadow */
.card-brutal-soft {
  background: white;
  border: 1px solid var(--color-ink);
  box-shadow: 4px 4px 0 0 rgba(26, 31, 44, 0.15);
}

/* Minimal: border only */
.card-minimal {
  background: white;
  border: 1px solid var(--color-gray-200);
}
```

---

## 3. Links

```css
a {
  color: var(--color-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-thickness: 1px;
  transition: color 0.15s ease;
}

a:hover {
  color: var(--color-accent);
}

/* Navigation link (no underline until hover) */
.nav-link {
  text-decoration: none;
}

.nav-link:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
```

---

## 4. Tags/Labels

```css
/* Monospace, uppercase, minimal */
.tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-ink);
}

/* State variant */
.tag-muted {
  color: var(--color-gray-500);
  border-color: var(--color-gray-300);
}
```

---

## 5. Dividers

```css
hr {
  border: none;
  border-top: 1px solid var(--color-gray-200);
  margin: var(--space-8) 0;
}

/* Heavy divider */
hr.heavy {
  border-top: 2px solid var(--color-ink);
}
```

---

## 6. Badges (Minimal)

Only when semantically necessary.

```css
.badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-error { color: var(--color-error); }
.badge-success { color: var(--color-success); }
.badge-warning { color: var(--color-warning); }
```

No backgrounds. No pills. Text color only.

---

## 7. Loading States

```css
/* Pulse for active processing */
.loading-pulse {
  width: 8px;
  height: 8px;
  background: var(--color-accent);
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Bar for determinate progress */
.loading-bar {
  height: 4px;
  background: var(--color-gray-200);
}

.loading-bar-fill {
  height: 100%;
  background: var(--color-ink);
  transition: width 0.2s ease;
}
```
