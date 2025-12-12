# Puppeteer v24.x API Reference

**Scope**: New v24.x commands only. Old API (`page.$`, `page.click`, `page.type`, `page.waitForSelector`) is assumed knowledge.

---

## Locator API

Locators auto-wait for elements and auto-retry on failure.

### `page.locator(selector).click()`

Auto-wait + auto-retry click. Replaces `page.$()` + `el.click()`.

```javascript
await page.locator('button.bg-burgundy').click();
```

### `locator.fill(text)`

Auto-detect input type (text, select, contenteditable). Replaces `page.type()`.

```javascript
await page.locator('input[name="email"]').fill('test@example.com');
```

### `locator.filter(fn)`

Filter elements before action. `fn` runs in page context.

```javascript
await page
  .locator('button')
  .filter(btn => btn.innerText === 'Dev Login')
  .click();
```

### `locator.setWaitForEnabled(bool)`

Wait for disabled→enabled before action.

```javascript
await page
  .locator('button[type="submit"]')
  .setWaitForEnabled(true)
  .click();
```

### `locator.on(LocatorEvent.Action, fn)`

Debug hook before each action/retry. May fire multiple times on retry.

```javascript
import { LocatorEvent } from 'puppeteer';

await page
  .locator('button')
  .on(LocatorEvent.Action, () => console.log('About to click'))
  .click();
```

---

## Video Recording

### `page.screencast({path})`

Record page activity. Requires ffmpeg. Returns `ScreenRecorder` with `.stop()`.

```javascript
const recorder = await page.screencast({ path: '/tmp/test.webm' });
// ... perform actions ...
await recorder.stop();
```

**Options**:
- `format`: `'webm'` (default) or `'gif'`
- `fps`: Frame rate (default: 30, gif: 20)
- `quality`: 0-63, lower = better (default: 30)
- `scale`: Output scale multiplier (default: 1)

---

## Media Emulation

### `page.emulateMediaFeatures([{name, value}])`

Test dark mode, reduced motion, color-gamut.

```javascript
await page.emulateMediaFeatures([
  { name: 'prefers-color-scheme', value: 'dark' }
]);
```

**Supported features**:
- `prefers-color-scheme`: `'light'` | `'dark'`
- `prefers-reduced-motion`: `'no-preference'` | `'reduce'`
- `prefers-reduced-transparency`: `'no-preference'` | `'reduce'`

---

## Cross-Browser (WebDriver BiDi)

### `launch({browser, protocol})`

Firefox uses WebDriver BiDi by default. Chrome needs explicit config.

```javascript
// Firefox - BiDi by default
const firefox = await puppeteer.launch({ browser: 'firefox' });

// Chrome - explicit BiDi
const chrome = await puppeteer.launch({
  browser: 'chrome',
  protocol: 'webDriverBiDi'
});
```

**Note**: Some CDP features throw `UnsupportedOperation` over BiDi.
