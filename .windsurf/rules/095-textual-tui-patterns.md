---
description: Textual TUI development patterns and corrections to AI training data
globs:
alwaysApply: false
---
# 095: Textual TUI Patterns

## 1. Container Types

### 1.1. Scrollable Containers
- **MUST** use `VerticalScroll` for scrollable vertical layouts
- **FORBIDDEN**: `Vertical` with `overflow-y: auto` hack - does not work
- **Source**: `textual.containers.VerticalScroll` (built-in scrollbar)

```python
from textual.containers import VerticalScroll

with VerticalScroll(id="form"):
    yield Input(...)
```

### 1.2. CSS for Scrollable Containers
```css
#form {
    height: 20;  /* No overflow-y needed - VerticalScroll handles it */
}
```

### 1.3. Horizontal Rows (Field + Button)
- **RECOMMENDED**: Use `HorizontalGroup` for single-row combinations (non-expanding, `height: auto`)
- **FORBIDDEN**: Using `Horizontal` for form rows; default CSS sets `height: 1fr`, collapsing the row in scroll containers
- **Layout**: Apply `classes="file-row"` (or similar) and style with `width: 1fr` on the input, `margin-left: 1` on the button
- **Reference**: `textual.containers.HorizontalGroup` API docs

## 2. Select Widget

### 2.1. Component Structure
- **Official**: "This widget has no component classes"
- **FORBIDDEN**: Assuming SelectCurrent CSS selector exists in docs
- **Reality**: SelectCurrent exists in source but not documented as stylable

### 2.2. Height Handling
- **Default**: `height: auto` from widget source
- **FORBIDDEN**: Forcing `height: 3` - clips selected value display
- **REQUIRED**: Let Select use native `height: auto`

```css
/* ✅ CORRECT */
.field-select {
    margin-bottom: 1;
}

/* ❌ WRONG - clips content */
.field-select {
    height: 3;
    background: $surface-lighten-1;
    border: solid $accent;
}
```

## 3. App Title

### 3.1. Class Variable (Uppercase)
```python
from textual.app import App

class MyApp(App):
    TITLE = "App Title"  # Uppercase TITLE, not lowercase title
    CSS = APP_CSS
```

### 3.2. Dynamic Setting
```python
def on_mount(self) -> None:
    self.title = "Dynamic Title"
    self.sub_title = "Subtitle"
```

## 4. Button Layout

### 4.1. Equal Distribution
```css
#actions {
    layout: horizontal;
}

#actions Button {
    width: 1fr;  /* Equal expansion */
    margin: 0 1 0 0;  /* Gap between buttons */
}

#actions Button:last-child {
    margin-right: 0;
}
```

## 5. Widget Styling

### 5.1. Native Styling Priority
- **FORBIDDEN**: Overriding `background` and `border` on Input/Select
- **REASON**: Conflicts with native focus states
- **REQUIRED**: Let widgets use default Textual styling

```css
/* ✅ CORRECT */
.field-input {
    margin-bottom: 1;
    height: 3;
    padding: 0 1;
}

/* ❌ WRONG - fights native styling */
.field-input {
    background: $surface-lighten-1;
    border: solid $accent;
}
```

## 6. TextLog Wrapping

### 6.1. No Native wrap Parameter
- **FORBIDDEN**: `TextLog(wrap=True)` - parameter does not exist
- **REQUIRED**: Manual text wrapping before write

```python
import textwrap

def wrap_log_message(message: str, width: int = 82) -> str:
    return textwrap.fill(
        message,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
        subsequent_indent="  ",
    )

log_widget.write(wrap_log_message("Long message..."))
```

### 6.2. CSS Overflow Control
```css
#result {
    height: 5;
    overflow-x: hidden;  /* Prevent horizontal scroll */
}
```

## 7. Spacing Control

### 7.1. Margin vs Padding
- **Margin**: Space outside widget
- **Padding**: Space inside widget (added to content area)
- **PATTERN**: Use `padding` for internal spacing, `margin` for widget separation

```css
/* Tight spacing between sections */
#actions {
    margin-bottom: 0;
}

#instructions {
    margin-top: 0;
    padding-top: 1;  /* Internal spacing */
}
```

## 8. Documentation Sources

### 8.1. Priority Order
1. Official Textual docs (<https://textual.textualize.io>)
2. Source code (github.com/Textualize/textual)
3. AI training data (outdated, verify against docs)

### 8.2. Version Compatibility
- **REQUIRED**: Check docs for Textual 0.40+ (2024-2025)
- **FORBIDDEN**: Assuming parameters/CSS from training data without verification

## 9. Worker Patterns (Background Processing)

### 9.1. Import Path (CRITICAL - Training Data is WRONG)
```python
# ✅ CORRECT (Textual 6.5.0+)
from textual import work

# ❌ WRONG - ImportError: cannot import name 'work' from 'textual.worker'
from textual.worker import work
```

**Source**: <https://textual.textualize.io/guide/workers/> (Textual 6.5.0)
**Lesson**: NEVER trust training data for Textual imports. ALWAYS verify.

### 9.2. Worker Decorator Usage
```python
from textual import work

class MyApp(App):
    @work(thread=True, exclusive=True, exit_on_error=False)
    async def _long_running_task(self) -> None:
        """Run CPU-bound work in background thread."""
        # Update UI from thread using call_from_thread
        self.call_from_thread(log_widget.write_line, "Processing...")

        # Long computation here
        result = expensive_computation()

        self.call_from_thread(log_widget.write_line, "Complete!")
```

### 9.3. Worker Parameters
- `thread=True` - **REQUIRED** for CPU-bound/blocking operations
- `exclusive=True` - Cancels previous workers before starting new one
- `exit_on_error=False` - Prevents app crash on worker exceptions

### 9.4. Thread Safety
- **FORBIDDEN**: Direct widget updates from worker thread
- **REQUIRED**: Use `self.call_from_thread(widget_method, args)` for all UI updates
- **REASON**: Textual is not thread-safe

```python
# ✅ CORRECT
self.call_from_thread(log_widget.write_line, "Message")

# ❌ WRONG - Race conditions, crashes
log_widget.write_line("Message")
```

## 10. Log Widget Family (CRITICAL Differences)

### 10.1. Widget Comparison

| Widget | Markup Support | Methods | Use Case |
|--------|---------------|---------|----------|
| `Log` | ❌ Plain text only | `write()`, `write_line()`, `write_lines()` | Simple logs |
| `RichLog` | ✅ With `markup=True` | `write()`, `clear()` | Formatted output |

### 10.2. Log Widget (Plain Text)
```python
from textual.widgets import Log

# No markup parameter exists
log = Log(id="result", highlight=False, auto_scroll=True)

# Rich markup displays literally
log.write_line("[green]Text[/]")  # Output: [green]Text[/]
```

### 10.3. RichLog Widget (Markup Support)
```python
from textual.widgets import RichLog

# markup=True enables Rich console markup
log = RichLog(id="result", markup=True, wrap=True, auto_scroll=True)

# Rich markup renders as colored/styled text
log.write("[green]Success![/]")  # Output: Success! (in green)
```

**Source**: <https://textual.textualize.io/widgets/rich_log/>

### 10.4. Method Differences
- **Log**: Has `write()`, `write_line()`, `write_lines()`
- **RichLog**: Has `write()`, `clear()` only (no write_line)

```python
# Log widget
log.write_line("Each call is a new line")

# RichLog widget
richlog.write("Each call is a new entry")  # Behaves like write_line
```

## 11. Text Display Behavior (CRITICAL Understanding)

### 11.1. Log.write() vs Log.write_line()
```python
log = Log()

# write() treats entire input as single content block
# Ignores embedded newlines (\n)
log.write("Line 1\nLine 2\nLine 3")  # Displays as truncated single line

# write_line() adds content as separate line entry
log.write_line("Line 1")  # Each call creates new line
log.write_line("Line 2")
log.write_line("Line 3")
```

**Lesson**: `write()` is NOT equivalent to `write_line()`. Use `write_line()` for line-by-line logs.

### 11.2. Text Wrapping with CSS
```css
#result {
    text-wrap: wrap;     /* Enables word wrapping */
    overflow-x: hidden;  /* No horizontal scroll */
}
```

**IMPORTANT**:
- `text-wrap: wrap` must be EXPLICIT (not always default)
- Applies to ALL Log widget family members
- Works with `write_line()` for proper line wrapping

### 11.3. OBSOLETE Pattern (Manual Wrapping)
```python
# ❌ OBSOLETE - Don't use with write_line() + CSS text-wrap
import textwrap
wrapped = textwrap.fill(message, width=80)
log.write(wrapped)  # write() ignores \n, defeats wrapping
```

**Correct modern pattern**:
```python
# ✅ Use write_line() + CSS text-wrap
log.write_line(message)  # Auto-wraps via CSS
```

## 12. Import Verification Protocol

### 12.1. Trust Hierarchy
1. **Official Docs** (textual.textualize.io) - PRIMARY SOURCE
2. **Test in Shell** (`pdm run python -c "import ..."`) - VERIFICATION
3. **Training Data** - NEVER trust without verification

### 12.2. Verification Examples

**Before using ANY Textual import:**
```bash
# Verify import path
pdm run python -c "from textual import work; print(work)"
pdm run python -c "from textual.widgets import RichLog; print(RichLog)"

# Check constructor parameters
pdm run python -c "from textual.widgets import Log; import inspect; print(inspect.signature(Log.__init__))"
```

### 12.3. Known Training Data Errors
- ✅ `from textual import work`
  ❌ `from textual.worker import work` (ImportError)

- ✅ `RichLog(markup=True)` for Rich markup
  ❌ `Log(markup=True)` (parameter doesn't exist)

- ✅ `Log.write_line()` for line-by-line
  ❌ Assuming `RichLog.write_line()` exists (method doesn't exist)

- ✅ `text-wrap: wrap` CSS for wrapping
  ❌ `Log(wrap=True)` parameter (doesn't exist)

### 12.4. Documentation URLs (Textual 6.5.0)
- Workers: <https://textual.textualize.io/guide/workers/>
- Log widget: <https://textual.textualize.io/widgets/log/>
- RichLog widget: <https://textual.textualize.io/widgets/rich_log/>
- CSS Properties: <https://textual.textualize.io/styles/text_wrap/>
- API Reference: Use search at <https://textual.textualize.io/api/>
