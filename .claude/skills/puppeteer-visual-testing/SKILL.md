---
name: puppeteer-visual-testing
description: Screenshot capture and visual testing with Puppeteer v24.x for Vue frontend.
---

# Puppeteer Visual Testing

## When to Use

- After creating/modifying Vue components
- Verify visual changes after CSS updates
- Validate mobile/responsive layouts
- Mentions: "screenshot", "visual test", "visual regression"

## Prerequisites

- Dev server running: `pnpm dev` (or `pdm run fe-dev`)
- Puppeteer v24.x installed
- ffmpeg installed (for screencast)

## Output

All screenshots/recordings go to `/tmp/` with descriptive names:
- `/tmp/dashboard-mobile-375x667.png`
- `/tmp/hamburger-open.png`
- `/tmp/dark-mode-test.webm`

## Auth Requirement

If testing authenticated routes, click "Dev Login" button first:

```javascript
await page.locator('button').filter(b => b.innerText === 'Dev Login').click();
```

## Quick Workflow

```javascript
import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 667 }); // Mobile-first
await page.goto('http://localhost:5173/app/dashboard');
await page.locator('.dashboard-layout').wait();
await page.screenshot({ path: '/tmp/dashboard-mobile.png' });
await browser.close();
```

## Routes

| Route | Description |
|-------|-------------|
| `/` | Landing page |
| `/login` | Auth page |
| `/app/dashboard` | Teacher dashboard |

## Reference

- [reference.md](reference.md) - v24.x API (locator, screencast, emulateMediaFeatures)
- [patterns.md](patterns.md) - Copy-paste test patterns
