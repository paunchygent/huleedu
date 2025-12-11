---
name: puppeteer-visual-testing
description: Screenshot capture and visual testing with Puppeteer MCP for Vue frontend.
---

# Puppeteer Visual Testing

## When to Use

- Capture screenshots of Vue components
- Verify visual changes after CSS updates
- Mentions: "screenshot", "visual test", "visual regression"

## Workflow

```
puppeteer_launch
puppeteer_new_page
puppeteer_navigate          → http://localhost:5173/app/dashboard
puppeteer_wait_for_selector → .dashboard-layout
puppeteer_screenshot
puppeteer_close_browser
```

## Tools

| Tool | Use |
|------|-----|
| `puppeteer_launch` | Start browser |
| `puppeteer_new_page` | Create tab |
| `puppeteer_navigate` | Go to URL |
| `puppeteer_wait_for_selector` | Wait for element |
| `puppeteer_screenshot` | Capture |
| `puppeteer_evaluate` | Run JS (set viewport) |
| `puppeteer_close_browser` | Cleanup |

## Routes

- `/` Landing
- `/login` Auth
- `/app/dashboard` Dashboard

## Viewports

```javascript
// Via puppeteer_evaluate
page.setViewport({ width: 375, height: 812 })   // Mobile
page.setViewport({ width: 768, height: 1024 })  // Tablet
page.setViewport({ width: 1280, height: 800 })  // Desktop
```

## Selectors

- `.dashboard-layout` - Dashboard loaded
- `.ledger-row` - Table rows
- `button.bg-burgundy` - Primary button

## Prereq

- Dev server running: `pdm run fe-dev`
- Puppeteer MCP configured in `.mcp.json` (project scope)
