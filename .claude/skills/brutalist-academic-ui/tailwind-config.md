# Tailwind Configuration

**Responsibility**: Brutalist constraints for Tailwind.

---

## tailwind.config.js

```javascript
module.exports = {
  theme: {
    fontFamily: {
      'serif': ['Source Serif 4', 'Georgia', 'serif'],
      'sans': ['IBM Plex Sans', 'system-ui', 'sans-serif'],
      'mono': ['IBM Plex Mono', 'SF Mono', 'monospace'],
    },
    borderRadius: {
      'none': '0',
      'sm': '2px',
      'DEFAULT': '4px',
      'md': '6px',
      'lg': '8px',
      // No xl, 2xl, 3xl, full - intentionally restricted
    },
    extend: {
      colors: {
        'ink': '#1a1a1a',
        'paper': '#fafaf9',
        'accent': '#2563eb',
      },
      maxWidth: {
        'prose': '65ch',
      },
    },
  },
}
```

---

## Banned Classes

```javascript
const bannedClasses = [
  'rounded-xl', 'rounded-2xl', 'rounded-3xl', 'rounded-full',
  'shadow-xl', 'shadow-2xl',
  'backdrop-blur',
  'bg-gradient-to-',
  'from-purple', 'to-purple',
  'animate-bounce',
];
```
