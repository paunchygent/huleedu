# HuleEdu Puppeteer Test Patterns

**Responsibility**: Copy-paste ready patterns using real selectors from the codebase.

---

## 1. Mobile Hamburger Navigation

Test drawer open/close on mobile viewport.

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 667 });
await page.goto('http://localhost:5173/app/dashboard');

// Open drawer
await page.locator('button[aria-label="Oppna meny"]').click();
await page.locator('.drawer-backdrop').wait();
await page.screenshot({ path: '/tmp/drawer-open.png' });

// Verify nav items visible
await page.locator('.drawer-nav-item').wait();

// Close drawer
await page.locator('button[aria-label="Stang meny"]').click();
await browser.close();
```

---

## 2. Dev Login → Dashboard

Authenticate and verify dashboard loads.

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 667 });
await page.goto('http://localhost:5173/login');

// Click Dev Login
await page
  .locator('button')
  .filter(btn => btn.innerText.includes('Dev Login'))
  .click();

// Wait for dashboard sections
await page.locator('h2').filter(h => h.innerText.includes('Kräver åtgärd')).wait();
await page.screenshot({ path: '/tmp/dashboard-loaded.png' });
await browser.close();
```

---

## 3. Ledger Row State Testing

Capture rows in different states (attention, processing, complete).

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 }); // Desktop for full table

await page.goto('http://localhost:5173/app/dashboard');

// Wait for ledger to load
await page.locator('.bg-white.border-2.border-navy').wait();

// Screenshot attention state rows
const attentionRows = await page.$$('[data-state="attention"]');
if (attentionRows.length) {
  await page.screenshot({ path: '/tmp/ledger-attention-rows.png' });
}

// Screenshot processing rows with progress bar
const processingRows = await page.$$('[data-state="processing"]');
if (processingRows.length) {
  await page.locator('.progress-track').wait();
  await page.screenshot({ path: '/tmp/ledger-processing.png' });
}

await browser.close();
```

---

## 4. Action Card Interaction

Test "Kräver åtgärd" cards and their buttons.

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 667 });
await page.goto('http://localhost:5173/app/dashboard');

// Wait for action card
await page.locator('.bg-white.border-2.border-navy.shadow-brutal').wait();

// Screenshot card with countdown timer
await page.screenshot({ path: '/tmp/action-card.png' });

// Click primary action button (burgundy)
await page
  .locator('.btn-brutal.bg-burgundy')
  .setWaitForEnabled(true)
  .click();

await browser.close();
```

---

## 5. Responsive Layout Comparison

Capture same view at mobile and desktop breakpoints.

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();

const viewports = [
  { width: 375, height: 667, name: 'mobile' },
  { width: 768, height: 1024, name: 'tablet' },
  { width: 1280, height: 800, name: 'desktop' }
];

await page.goto('http://localhost:5173/app/dashboard');

for (const vp of viewports) {
  await page.setViewport({ width: vp.width, height: vp.height });
  await page.waitForTimeout(100); // Allow layout reflow
  await page.screenshot({ path: `/tmp/dashboard-${vp.name}.png`, fullPage: true });
}

await browser.close();
```

---

## 6. Animation Recording (Drawer Transition)

Record drawer slide animation for visual validation.

```javascript
const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 375, height: 667 });
await page.goto('http://localhost:5173/app/dashboard');

const recorder = await page.screencast({ path: '/tmp/drawer-transition.webm' });

// Open drawer
await page.locator('button[aria-label="Oppna meny"]').click();
await new Promise(r => setTimeout(r, 400));

// Close drawer
await page.locator('button[aria-label="Stang meny"]').click();
await new Promise(r => setTimeout(r, 400));

await recorder.stop();
await browser.close();
```

---

## Real Selectors Reference

| Element | Selector |
|---------|----------|
| Hamburger open | `button[aria-label="Oppna meny"]` |
| Hamburger close | `button[aria-label="Stang meny"]` |
| Drawer backdrop | `.drawer-backdrop` |
| Drawer nav item | `.drawer-nav-item` |
| Ledger table | `.bg-white.border-2.border-navy` |
| Attention row | `[data-state="attention"]` |
| Processing row | `[data-state="processing"]` |
| Progress bar | `.progress-track` |
| Action card | `.bg-white.border-2.border-navy.shadow-brutal` |
| Primary button | `.btn-brutal.bg-burgundy` |
| Logout | `button` + filter `Logga ut` |
| Section header | `h2` + filter `Kräver åtgärd` |
