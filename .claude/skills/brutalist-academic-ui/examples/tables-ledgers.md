# Tables and Ledgers

**Responsibility**: Data tables as information architecture. State through structure.

---

## 1. Ledger Structure

```css
.ledger {
  width: 100%;
  border: 2px solid var(--color-ink);
  background: white;
}

.ledger-header {
  display: grid;
  border-bottom: 2px solid var(--color-ink);
  background: var(--color-gray-100);
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ledger-row {
  display: grid;
  border-bottom: 1px solid var(--color-ink);
  background: white;
  cursor: pointer;
}

.ledger-cell {
  padding: var(--space-4);
  border-right: 1px solid var(--color-ink);
}

.ledger-cell:last-child {
  border-right: none;
}
```

---

## 2. State Through Structure

State is communicated through structural changes, not decorative badges.

### Processing State

```html
<div class="ledger-row border-l-4 border-l-accent" data-state="processing">
  <div class="ledger-cell">
    <span class="font-mono text-xs uppercase tracking-wide text-accent">Processing</span>
  </div>
  <div class="ledger-cell">
    <div class="h-2 w-2 bg-accent rounded-full animate-pulse"></div>
  </div>
</div>
```

### Attention Required

```html
<div class="ledger-row border-b-2 border-accent bg-accent/[0.03]" data-state="attention">
  <div class="ledger-cell">
    <span class="font-mono text-xs uppercase tracking-wide text-accent font-bold">Action</span>
  </div>
</div>
```

### Complete State

```html
<div class="ledger-row" data-state="complete">
  <div class="ledger-cell">
    <span class="font-mono text-xs uppercase tracking-wide text-ink/40">Done</span>
  </div>
</div>
```

---

## 3. Row Hover

```css
/* Hard outline, background shift */
.ledger-row:hover {
  background: var(--color-gray-100);
  outline: 2px solid var(--color-ink);
  outline-offset: -2px;
  position: relative;
  z-index: 1;
}

/* Underline on primary text */
.ledger-row:hover .ledger-title {
  text-decoration: underline;
  text-decoration-thickness: 2px;
  text-underline-offset: 4px;
}

/* Banned */
.ledger-row:hover {
  box-shadow: 0 10px 40px rgba(0,0,0,0.1); /* No */
  transform: scale(1.01); /* No */
}
```

---

## 4. State Transitions (Websocket)

Brief flash on state change. Not bounce, not slide.

```css
@keyframes state-change {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(37, 99, 235, 0.08); }
}

.ledger-row[data-state-changed] {
  animation: state-change 0.4s ease;
}
```

```javascript
row.setAttribute('data-state-changed', '');
row.addEventListener('animationend', () => {
  row.removeAttribute('data-state-changed');
}, { once: true });
```

---

## 5. Progress Indicators

```css
.progress-track {
  width: 100%;
  height: 6px;
  background: var(--color-gray-200);
  /* No border-radius. A bar is a bar. */
}

.progress-fill {
  height: 100%;
  background: var(--color-ink);
  transition: width 0.3s ease;
}

.progress-fill[data-active] {
  background: var(--color-accent);
}
```

---

## 6. Anti-Patterns

- **Status badges/pills**: `bg-yellow-100 text-yellow-800 rounded-full` = decorating, not communicating
- **Multiple competing colors**: One accent for attention. Everything else is ink or muted.
- **Icons for every state**: Checkmark next to "Complete" is redundant
- **Animated progress for complete items**: If done, it's done.
- **Hover effects that obscure**: Enhance readability, don't compete with it.
