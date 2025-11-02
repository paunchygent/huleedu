"""Help screen for CJ Pair Generator TUI."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Markdown

HELP_CONTENT = """
# CJ Pair Generator Help

Press **ESC**, **F1**, or **?** to close this help screen.

## Quick Navigation

- [Student Input Fields](#student-input-fields)
- [Anchor Configuration](#anchor-configuration)
- [Rater Setup](#rater-setup)
- [Output Paths](#output-paths)
- [Comparison Design Settings](#comparison-design-settings)
- [Workflow Overview](#workflow-overview)
- [Multi-Session Strategy](#multi-session-strategy)
- [Anchor Ladder Guidance](#anchor-ladder-guidance)
- [Tips and Shortcuts](#tips-and-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Back to Top](#cj-pair-generator-help)

## Purpose

This TUI guides you through creating statistically efficient comparison schedules for Comparative Judgment (CJ). Provide student essays, optional anchor essays, and rater workload preferences to generate:

- A balanced set of comparison pairs (optimized for information gain)
- Rater-specific assignment lists (who judges which pair)

The form is grouped into **Student Input**, **Anchor Configuration**, **Rater Setup**, **Comparison Design Settings**, and **Output Paths**. Every field below explains why it matters, how to fill it in, and when to leave it blank.

## Student Input Fields

### Students CSV
**Purpose**: Load a large student roster straight from a CSV so you avoid manual typing.

**Format**: Absolute or relative path to a CSV that contains a column named `essay_id`, `student_id`, or `id`. The loader searches in that order.

**When to use**: Recommended for cohorts above ~20 students or whenever you already have a spreadsheet export.

**Example**: `data/session2_students.csv`

**Notes**: Leave this blank if you prefer manual entry. The generator cannot run unless it can collect student IDs from either this file or the manual field.

### Students (Manual Entry)
**Purpose**: Provide quick comma-separated IDs without preparing a CSV.

**Format**: Comma-separated list with optional spaces. Case-insensitive trim is applied.

**When to use**: Small pilots, dry runs, or whenever you only have a handful of essays (typically < 20).

**Example**: `JA24, II24, ES24`

**Notes**: If both CSV and manual fields are filled, the CSV wins. Manual entry is still shown in logs so you can verify what was parsed.

[Back to top](#cj-pair-generator-help)

## Anchor Configuration

### Anchors (Custom Ladder)
**Purpose**: Supply pre-graded benchmark essays so raters have known reference points across the grade scale.

**Format**: Comma-separated IDs where the ID itself encodes the grade level (letters, numbers, or any notation your team uses).

**When to use**: Whenever you have calibration essays and want the comparison design to ensure students are compared against them.

**Example**: `F+1, F+2, D1, C1, C2, B1, B2, B3, A1, A2, A3`

**Notes**: If left blank, the tool automatically uses a 12-anchor ladder from F+ through A3. Include the grade in each ID so raters instantly recognize the level (e.g., `B1`, `B2`). Use numbering (1, 2, 3) to distinguish anchors at the same grade. Any grading schema works—from A-F to numeric rubrics such as `1.0, 2.5, 5.0`. Anchor IDs appear in outputs exactly as you type them.

### Include Anchor-Anchor Comparisons
**Purpose**: Decide whether anchors are scheduled against each other in addition to student comparisons.

**Format**: Dropdown with `Yes` (default) or `No`.

**When to use**: Keep at `Yes` for calibration sessions where you expect raters to revisit the anchor ladder. Switch to `No` only if anchor performance is already stable and you want to devote all comparisons to student essays.

**Example**: Selecting `Yes` ensures the design can include pairs like `B1 vs A2`.

**Notes**: Turning this off still allows anchor-vs-student comparisons. The setting propagates into the D-optimal design spec before optimization.

[Back to top](#cj-pair-generator-help)

## Output Paths

### Assignments CSV Path
**Purpose**: Choose where rater-specific assignments are written once the generator finishes.

**Format**: File path (relative paths resolve against the TUI working directory).

**When to use**: Always. The generator needs a target file to save assignments.

**Example**: `cj_rater_assignments.csv`

**Notes**: Must point to a file, not a directory. Existing files are overwritten after confirmation in logs, so keep backups if needed.

### Comparison Pairs Output
**Purpose**: Persist the complete set of comparison pairs before they are distributed to raters.

**Format**: File path, similar rules as the assignments output.

**When to use**: Always. This file captures the comparison design and can be reused in future sessions.

**Example**: `cj_comparison_pairs.csv`

**Notes**: The file contains every comparison the generator produced, including anchor-anchor when enabled. Use it as the source when regenerating assignments without re-running the design step.

[Back to top](#cj-pair-generator-help)

## Rater Setup

### Number of Raters
**Purpose**: Declare how many raters will participate when you do not have a named roster.

**Format**: Positive integer (defaults to 14).

**When to use**: Anonymous or rotating rater pools where you just need `Rater_1` … `Rater_N`.

**Example**: `12`

**Notes**: Leave blank if you provide explicit names. The total number of pair slots equals `rater_count × comparisons per rater`.

### Explicit Rater Names
**Purpose**: Generate assignments labeled with exact rater identities.

**Format**: Comma-separated list. Wrap names containing commas in quotes.

**When to use**: Coaching scenarios, pilot studies, or any workflow where raters require personalized files.

**Example**: `"Burns, Ann", "Roth, Lena", "Davis, Marcus"`

**Notes**: If this field is filled, the `Number of Raters` value is ignored. The tool deduplicates trimmed names but keeps order.

### Comparisons Per Rater
**Purpose**: Set the workload each rater should receive.

**Format**: Positive integer (defaults to 10).

**When to use**: Always—this controls how many pairs are assigned per rater.

**Example**: `8`

**Notes**: The requested total comparisons equals `rater count × this value`. The generator attempts to deliver exactly that many pairs; the final count is reported in the log.

[Back to top](#cj-pair-generator-help)

## Comparison Design Settings

### Previous Session CSV
**Purpose**: Prevent duplicate comparisons by importing results from a prior session.

**Format**: File path to a CSV generated by this tool (either pairs or assignments file).

**When to use**: Sessions 2 and beyond. Load Session 1 output here so the tool excludes pairs already judged.

**Example**: `archives/2025-03-01/session1_pairs.csv`

**Notes**: Leave blank for Session 1. The loader tolerates additional columns and only reads pair identifiers.

### Locked Pairs
**Purpose**: Force specific essay comparisons into the schedule regardless of the automatic design.

**Format**: Semicolon-separated list of comma-separated essay IDs. Example pattern: `essay_a,essay_b; essay_c,essay_d`.

**When to use**: Research requirements, deliberate cross-grade checks, or when you must replicate comparisons from prior studies.

**Example**: `JA24,A1; II24,B1`

**Notes**: Whitespace is ignored. Invalid entries (missing commas) trigger a validation error so you can fix them before the design step starts.

### Max Repetitions Per Pair
**Purpose**: Cap how many times the same comparison can appear across the full schedule.

**Format**: Positive integer (default 3).

**When to use**: Always—this is the primary control for balancing reliability versus breadth.

**Example**: `2`

**Notes**: Lower numbers increase coverage (more unique comparisons). Higher numbers improve reliability by collecting multiple judgments on difficult pairs. Setting to 1 turns off repeats entirely.

[Back to top](#cj-pair-generator-help)

## How the Workflow Runs

1. **Prepare inputs**: Fill either Students CSV or Manual Entry (or both, but CSV wins). Add anchors if you have a custom ladder.
2. **Configure raters**: Set either the count or explicit names, plus comparisons per rater to define total workload.
3. **Tune optimization**: Supply previous sessions, locked pairs, and max repetitions to shape the design. Toggle anchor-anchor comparisons if needed.
4. **Choose output paths**: Confirm both the generated pairs path and assignments path point where you want the CSVs saved.
5. **Start generation**: Click **Generate Assignments** or press **g**. The button disables while the background worker runs.
6. **Optimization**: The D-optimal planner builds the most informative comparison set given your constraints.
7. **Assignment**: The redistribution step balances pairs across raters and writes the assignments CSV.
8. **Review logs**: The RichLog on the main screen shows chosen inputs, validation warnings, total comparisons requested vs available, and file locations.

[Back to top](#cj-pair-generator-help)

## Multi-Session Strategy

- **Session 1**: Leave `Previous Session CSV` blank. The tool starts from scratch using your student and anchor lists.
- **Session 2+**: Load the prior `Comparison Pairs Output` or `Assignments CSV`. The tool removes those pairs from consideration, then fills the remaining quota with new comparisons.
- **Gap analysis**: After each run, compare the new assignments count with the requested total. If fewer pairs were available, consider increasing `Max Repetitions Per Pair`, adding anchors, or expanding the rater pool.

[Back to top](#cj-pair-generator-help)

## Anchor Ladder Guidance

- Anchors should span your entire grade scale so the design can place students relative to known benchmarks.
- Prefix or suffix the ID with the grade (e.g., `C2`, `B3`, `A1`) so raters know what level they are judging.
- Use multiple anchors per grade when possible (e.g., `F+1`, `F+2`) to capture variability within the same band.
- Any notation works (letters, numbers, rubric levels). Consistency matters more than format.
- If anchor essays are unavailable, leave the field blank—the default ladder inserts placeholders you can swap later.

[Back to top](#cj-pair-generator-help)

## Tips and Shortcuts

### Keyboard shortcuts
- `g`: Generate assignments (same as clicking the button).
- `F1` or `?`: Reopen this help screen.
- `q`: Quit the TUI.
- `Tab` / `Shift+Tab`: Navigate between inputs.
- `Enter`: Activate the focused button.

### Drag-and-drop paths
- Focus any file path input and drag a file from your file explorer onto the terminal to auto-fill the absolute path.

### Reset quickly
- Click **Reset** to restore defaults when switching projects or trying alternative parameter sets.

### Watch the totals
- The log reports requested versus available comparisons. If the available total is lower, adjust rater count, workload per rater, or max repeats.

### Personalized assignments
- Provide explicit rater names to distribute work across specific people. Leave the field blank to auto-generate `Rater_1`, `Rater_2`, etc.

### Balancing reliability and coverage
- Higher `Max Repetitions Per Pair` yields more repeat judgments and higher reliability.
- Lower max repeats, a larger rater pool, or disabling anchor-anchor comparisons increases unique student-student pairs.
- Schedule at least one calibration session with anchor-anchor comparisons enabled so raters realign on the ladder.

### After generation
- Open the **Comparison Pairs Output** file to review overall coverage and anchor placement.
- Share the **Assignments CSV** with raters; each row lists a rater and their assigned essay IDs.
- Archive both outputs between sessions so you can supply them to `Previous Session CSV` and prevent duplicates.

[Back to top](#cj-pair-generator-help)

## Troubleshooting

- **Missing students**: Ensure the CSV contains `essay_id`, `student_id`, or `id`. For manual entry, separate IDs with commas.
- **Validation errors**: The log cites the problematic field. Fix the value and run again—no files are written until validation succeeds.
- **Output issues**: Confirm output paths point to files (not directories) and that the target location is writable.
- **Reusing files**: If paths change between sessions, update the form fields so the tool can locate the CSVs.
- **Unexpected pair counts**: Expand the rater pool, raise `Max Repetitions Per Pair`, or add more anchor/student essays to increase available comparisons.
- [Back to top](#cj-pair-generator-help)
"""


class HelpScreen(ModalScreen):
    """Help documentation modal screen."""

    CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen VerticalScroll {
        width: 80%;
        height: 80%;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    HelpScreen Markdown {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create help content display."""
        with VerticalScroll(id="help-scroll"):
            yield Markdown(HELP_CONTENT)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Scroll to in-document anchors instead of opening external links."""
        if event.href.startswith("#"):
            event.prevent_default()
            markdown = self.query_one(Markdown)
            markdown.goto_anchor(event.href[1:])

    def on_key(self, event) -> None:
        """Close help screen on ESC, F1, or ?."""
        if event.key in ("escape", "f1", "question_mark"):
            self.dismiss()
