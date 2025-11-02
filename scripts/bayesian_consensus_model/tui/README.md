# Redistribute TUI Module

Interactive terminal interface for generating optimized comparison pairs and distributing them to raters.

## Purpose

Provides a Textual-based TUI for the D-optimal pair optimizer and assignment generator. Replaces command-line workflow with form-driven interface supporting file drag-and-drop, multi-session workflows, and real-time validation.

## Architecture

The TUI separates concerns across five modules:

| Module | LoC | Responsibility |
|--------|-----|----------------|
| `redistribute_tui.py` | 168 | Event handling, widget queries, workflow orchestration |
| `form_layout.py` | 184 | Widget composition, CSS, field definitions |
| `file_drop_handler.py` | 87 | File path extraction, quote removal, paste handling |
| `workflow_executor.py` | 306 | Optimizer execution, assignment generation, validation |
| `result_formatter.py` | 101 | Log message formatting for optimization and assignment results |

## Module Reference

### redistribute_tui.py

Main application class and event handlers.

**Key Components:**

- `RedistributeApp(App)`: Main Textual application
- `compose()`: Delegates to `create_form_layout()`
- `on_input_changed()`: Strips quotes from file paths on change events
- `on_paste()`: Detects file paths in paste events and populates target fields
- `_generate_assignments()`: Orchestrates optimizer → assignment workflow
- `_reset_form()`: Resets all fields to defaults

**Keyboard Bindings:**

- `g`: Generate assignments
- `q`: Quit

**Usage:**

```bash
pdm run python -m scripts.bayesian_consensus_model.redistribute_tui
```

### form_layout.py

Form structure, CSS, and widget composition.

**Constants:**

- `DEFAULT_PAIRS_OUTPUT = Path("cj_comparison_pairs.csv")`
- `DEFAULT_OUTPUT = Path("cj_rater_assignments.csv")`
- `DEFAULT_RATER_COUNT = 14`

**Key Function:**

- `create_form_layout() -> ComposeResult`: Generates complete form layout with all input fields, labels, and containers

**Field IDs:**

- `students_csv_input`: Student roster CSV path
- `students_input`: Comma-separated student IDs (fallback)
- `anchors_input`: Custom anchor IDs (optional)
- `output_input`: Final assignments CSV path
- `rater_count_input`: Number of raters
- `rater_names_input`: Explicit rater names
- `per_rater_input`: Comparisons per rater
- `optimizer_output_input`: Comparison pairs CSV path
- `previous_csv_input`: Previous session CSV for multi-session workflows
- `locked_pairs_input`: Hard-locked pairs (semicolon-separated)
- `optimizer_max_repeat_input`: Max repetitions per pair
- `include_anchor_anchor_select`: Include anchor-anchor comparisons (yes/no)

**CSS Classes:**

- `.field-input`: Styled input fields
- `.field-select`: Styled select dropdowns
- `.field`: Field containers
- `#form`: Scrollable form container (height: 28)
- `#result`: Log output area (height: 5)
- `#actions`: Horizontal button container

**CSS Structure:**

```css
Screen: overflow-y auto, center top alignment
#panel: 80% width, max 90 columns, round border, boost background
.field-input: margin-bottom 1, height 3, surface-lighten-1 background
.field-select: margin-bottom 1, height 3, surface-lighten-1 background
```

### file_drop_handler.py

Handles file path extraction from paste events and quote removal.

**Constants:**

- `FILE_DROP_TARGET_IDS`: Set of input IDs that accept file paths
  - `students_csv_input`
  - `optimizer_output_input`
  - `previous_csv_input`
  - `output_input`

**Functions:**

`extract_paths_from_paste(paste_text: str) -> list[str]`

- Extracts file paths from pasted text
- Supports multiple delimiters: null byte (`\x00`), newline, comma, space
- Strips quotes (single and double)
- Removes `file://` prefix
- Expands `~` to home directory
- Validates paths exist before returning

`unquote_file_path(value: str) -> str | None`

- Removes surrounding quotes if present
- Returns unquoted path if file exists, else None
- Used by `on_input_changed()` handler to fix Finder drag-and-drop paths

**Quote Handling:**
macOS Finder wraps dragged file paths in single quotes when dropped into terminal applications. The `on_input_changed()` handler detects this and strips quotes automatically for file drop target fields.

### workflow_executor.py

Business logic for optimizer and assignment generation.

**Dataclasses:**

`OptimizerInputs`

- Extracted form values for optimizer
- Fields: students_csv, students_manual, anchors, optimizer_output, previous_csv, locked_pairs, max_repeat, include_anchor_anchor, rater_names, rater_count, per_rater

`AssignmentInputs`

- Extracted form values for assignment generator
- Fields: output_path, rater_names, rater_count, per_rater

`AssignmentResult`

- Assignment generation output
- Fields: quotas (dict), requested_total, available_total, output_path

**Functions:**

`extract_optimizer_inputs(query_one: callable) -> OptimizerInputs`

- Queries all optimizer-related form fields
- Returns populated OptimizerInputs dataclass

`extract_assignment_inputs(query_one: callable) -> AssignmentInputs`

- Queries all assignment-related form fields
- Returns populated AssignmentInputs dataclass

`run_optimizer(inputs: OptimizerInputs) -> tuple[OptimizationResult, Path, str]`

- Validates inputs (student source, output path, rater configuration)
- Loads students from CSV or manual entry
- Parses anchors, locked pairs, max repeat, include_anchor_anchor toggle
- Calculates total slots from rater count × per_rater
- Loads previous comparisons if provided
- Builds dynamic spec and runs optimizer
- Writes optimized design to CSV
- Returns: (optimization result, output path, students display value)

`generate_assignments(inputs: AssignmentInputs, pairs_path: Path) -> AssignmentResult`

- Validates output path and rater configuration
- Loads comparisons from pairs CSV
- Builds rater list from count or names
- Handles shortage scenario (requested > available)
- Generates type-aware balanced assignments
- Writes assignments CSV
- Returns: AssignmentResult with quotas and totals

**Validation:**

- Raises `ValueError` for invalid inputs (missing students, non-positive counts)
- Raises `FileNotFoundError` for missing CSV files

### result_formatter.py

Formats optimization and assignment results for log display.

**Functions:**

`format_optimization_summary(result: OptimizationResult, output_path: Path) -> list[str]`

- Returns list of formatted messages for optimization results
- Includes: log-det gains, slot requirements, type distribution, anchor coverage, repeat counts
- Uses Textual markup: `[green]`, `[yellow]` for status indicators

`format_assignment_summary(quotas: dict[str, int], requested_total: int, available_total: int, output_path: Path) -> list[str]`

- Returns list of formatted messages for assignment results
- Includes: shortage notice (if applicable), rater count/range, total allocations, output path
- Uses Textual markup for status indicators

## Usage

### Running the TUI

```bash
pdm run python -m scripts.bayesian_consensus_model.redistribute_tui
```

### Workflow Steps

1. **Load Students**
   - Recommended: Provide CSV with `essay_id`, `student_id`, or `id` column
   - Fallback: Enter comma-separated student IDs

2. **Configure Anchors** (optional)
   - Leave blank for default 12-anchor ladder
   - Provide custom anchor IDs if needed

3. **Set Output Paths**
   - Pairs CSV: Where optimizer saves optimized comparison pairs
   - Assignments CSV: Where final rater assignments are written

4. **Configure Raters**
   - Option A: Provide rater count (generates Rater_01, Rater_02, ...)
   - Option B: Provide explicit rater names (comma-separated)
   - Set comparisons per rater

5. **Optimization Settings**
   - Total slots: Rater count × per_rater (calculated automatically)
   - Max repetitions per pair (default: 3)
   - Previous session CSV (for multi-session workflows)
   - Locked pairs (semicolon-separated: essay_a,essay_b; essay_c,essay_d)
   - Include anchor-anchor comparisons (yes/no)

6. **Generate**
   - Press `g` or click "Generate Assignments"
   - Optimizer runs → saves pairs CSV
   - Assignment generator runs → saves assignments CSV
   - Log displays results with metrics

### File Drag-and-Drop

Focus any file path field and drag files from Finder onto the terminal window. The TUI automatically:

- Detects file paths in paste events
- Strips quotes added by Finder
- Populates the focused field (or students_csv_input by default)

Supported fields: students_csv_input, optimizer_output_input, previous_csv_input, output_input

## Extension Patterns

### Adding a New Input Field

1. **form_layout.py**: Add Label and Input widgets to `create_form_layout()`

```python
yield Label("New Field Description")
yield Input(
    placeholder="Placeholder text",
    id="new_field_input",
    classes="field-input",
)
```

2. **workflow_executor.py**: Update relevant dataclass and extraction function

```python
@dataclass
class OptimizerInputs:
    # existing fields...
    new_field: str

def extract_optimizer_inputs(query_one: callable) -> OptimizerInputs:
    return OptimizerInputs(
        # existing fields...
        new_field=query_one("#new_field_input", Input).value.strip(),
    )
```

3. **workflow_executor.py**: Use the new field in workflow logic

```python
def run_optimizer(inputs: OptimizerInputs) -> tuple[OptimizationResult, Path, str]:
    # Parse and use inputs.new_field
    ...
```

4. **redistribute_tui.py**: Add reset logic in `_reset_form()`

```python
def _reset_form(self) -> None:
    # existing resets...
    self.query_one("#new_field_input", Input).value = ""
```

If the field accepts file paths, add its ID to `FILE_DROP_TARGET_IDS` in `file_drop_handler.py`.

### Modifying Form Layout

Edit `APP_CSS` in `form_layout.py`:

```python
APP_CSS = """
#new_container {
    height: 10;
    border: solid $primary;
}
"""
```

Adjust widget structure in `create_form_layout()`:

```python
with Container(id="new_container"):
    yield Label("Section Title")
    yield Input(id="field1")
    yield Input(id="field2")
```

### Extending Workflow Logic

Add helper functions to `workflow_executor.py`:

```python
def validate_custom_constraint(inputs: OptimizerInputs) -> None:
    """Validate custom constraint logic."""
    if not inputs.some_field:
        raise ValueError("Custom constraint violated.")
```

Call from `run_optimizer()` or `generate_assignments()`:

```python
def run_optimizer(inputs: OptimizerInputs) -> tuple[OptimizationResult, Path, str]:
    validate_custom_constraint(inputs)
    # existing logic...
```

### Adding Output Messages

Extend formatters in `result_formatter.py`:

```python
def format_optimization_summary(result: OptimizationResult, output_path: Path) -> list[str]:
    messages = []
    # existing messages...
    messages.append(f"New metric: {result.new_metric}")
    return messages
```

Update `_generate_assignments()` in `redistribute_tui.py` to log new messages:

```python
for message in format_optimization_summary(opt_result, pairs_path):
    log_widget.write(message)
```

## Implementation Notes

### Form State Management

The `query_one()` method retrieves widget references by ID and type:

```python
students_input = self.query_one("#students_input", Input)
value = students_input.value.strip()
```

Widget values are extracted in `_generate_assignments()` via `extract_optimizer_inputs()` and `extract_assignment_inputs()`.

### Error Handling

Workflow functions raise exceptions for validation failures:

- `ValueError`: Invalid input values (missing required fields, non-positive counts)
- `FileNotFoundError`: Missing CSV files

The `_generate_assignments()` method catches these and logs to the result area:

```python
try:
    opt_result, pairs_path, students_value = run_optimizer(optimizer_inputs)
except (FileNotFoundError, ValueError) as error:
    log_widget.write(f"[red]Error:[/] {error}")
```

### File Path Quote Handling

macOS Finder wraps file paths in single quotes when dragged to terminal applications. The TUI strips quotes in two places:

1. **on_input_changed()**: Real-time quote removal as user types or drags files
2. **on_paste()**: Quote removal during paste event processing

Both use `unquote_file_path()` to validate the unquoted path exists before updating the field.

### Multi-Session Workflows

For Session 2+ comparisons:

1. Provide Session 1 pairs CSV in `previous_csv_input`
2. Optimizer loads previous comparisons via `load_previous_comparisons_from_csv()`
3. Coverage analysis ensures students without anchor coverage get required pairs
4. New comparisons complement existing coverage

### Locked Pairs Format

Semicolon-separated pairs, each pair comma-separated:

```
JA24,A1; II24,B1; ES24,B2
```

Parsed in `run_optimizer()` and passed to `load_dynamic_spec()` as hard constraints.

### Type-Aware Assignment Balancing

`workflow_executor.generate_assignments()` calls `assign_pairs()` from `redistribute_core`, which ensures:

- Every rater receives at least one student-anchor comparison (when available)
- Mixed workload across comparison types (student-student, student-anchor, anchor-anchor)
- Even distribution when shortage occurs (requested > available)

### Anonymization

Final assignments CSV receives auto-generated sequential display names (`essay_01`, `essay_02`, ...) for complete rater blinding. Original IDs preserved in optimizer pairs CSV for coordinator reference.
