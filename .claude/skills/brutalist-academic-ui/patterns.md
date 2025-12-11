# Brutalist Academic UI Patterns

**Responsibility**: Implementation templates. Copy-paste ready.

---

## 1. Academic Document Layout

For documentation, papers, institutional content.

```css
body {
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: var(--text-lg);
  line-height: var(--leading-relaxed);
  color: var(--color-ink);
  background: var(--color-paper);
}

.document {
  max-width: 800px;
  margin: 0 auto;
  padding: var(--space-16) var(--space-6);
}

.document h1 {
  font-size: var(--text-3xl);
  font-weight: 600;
  line-height: var(--leading-tight);
  margin-bottom: var(--space-8);
}

.document h2 {
  font-size: var(--text-xl);
  font-weight: 600;
  margin-top: var(--space-12);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-gray-200);
}

.document p + p {
  margin-top: var(--space-4);
}
```

---

## 2. Data-Heavy Interface

For dashboards, tables, system information.

```css
body {
  font-family: 'IBM Plex Mono', 'SF Mono', monospace;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  color: var(--color-ink);
  background: var(--color-gray-100);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

.data-table th,
.data-table td {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  border-bottom: 1px solid var(--color-gray-200);
}

.data-table th {
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: var(--text-xs);
  color: var(--color-gray-600);
}

.data-table tr:hover {
  background: var(--color-gray-200);
}
```

---

## 3. Navigation

```css
.nav {
  display: flex;
  gap: var(--space-8);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--color-ink);
}

.nav a {
  color: var(--color-ink);
  text-decoration: none;
  font-size: var(--text-sm);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.nav a:hover,
.nav a[aria-current="page"] {
  text-decoration: underline;
  text-underline-offset: 4px;
}
```

---

## 4. Grid Layout

```css
.layout {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: var(--space-8);
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 var(--space-12);
}

/* Sidebar + Content */
.layout-sidebar {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: var(--space-12);
}

/* Three columns */
.layout-thirds {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-8);
}
```

---

## 5. Section Rhythm

```css
section {
  padding: var(--space-24) 0;
}

section + section {
  border-top: 1px solid var(--color-gray-200);
}

.section-header {
  margin-bottom: var(--space-8);
}

.section-header h2 {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.section-header p {
  color: var(--color-gray-600);
  max-width: 65ch;
}
```
