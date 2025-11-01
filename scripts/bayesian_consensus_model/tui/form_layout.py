"""Form layout and UI structure for redistribute TUI."""

from __future__ import annotations

import textwrap
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

try:
    from textual.widgets import TextLog  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - compatibility with older Textual
    from textual.widgets import Log as TextLog  # type: ignore

DEFAULT_PAIRS_OUTPUT = Path("optimized_pairs.csv")
DEFAULT_OUTPUT = Path("session2_dynamic_assignments.csv")
DEFAULT_RATER_COUNT = 14
MAX_LOG_WIDTH = 82  # Fits within 90-column panel with padding

APP_CSS = """
Screen {
    overflow-y: auto;
    align: center top;
}

#panel {
    width: 80%;
    max-width: 90;
    border: round $primary;
    background: $boost;
}

.field-input {
    margin-bottom: 1;
    height: 3;
    padding: 0 1;
}

.field-select {
    margin-bottom: 1;
}

.field {
    width: 100%;
    margin-bottom: 1;
}

.field Label {
    padding-bottom: 0;
}

.field Input, .field Select {
    width: 100%;
}

#form {
    height: 20;
}

#result {
    height: 5;
    margin-top: 1;
    overflow-x: hidden;
    scrollbar-size: 1 1;
}

#actions {
    layout: horizontal;
    margin-top: 1;
    margin-bottom: 0;
    height: auto;
}

#actions Button {
    width: 1fr;
    margin: 0 1 0 0;
}

#actions Button:last-child {
    margin-right: 0;
}

#instructions {
    margin-top: 0;
    padding-top: 1;
}
"""


def create_form_layout() -> ComposeResult:
    """Generate the complete form layout for the redistribute TUI."""
    yield Header()
    with Container(id="panel"):
        with VerticalScroll(id="form"):
            yield Label("Students CSV (optional - recommended for large cohorts)")
            yield Input(
                placeholder="Path to CSV with essay_id/student_id/id column",
                id="students_csv_input",
                classes="field-input",
            )
            yield Label("Students (comma-separated - fallback if no CSV)")
            yield Input(
                placeholder="e.g., JA24, II24, ES24",
                id="students_input",
                classes="field-input",
            )
            yield Label("Anchors (optional - leave blank for default 12-anchor ladder)")
            yield Input(
                placeholder="Leave blank for default anchor ladder",
                id="anchors_input",
                classes="field-input",
            )
            yield Label("Assignments CSV Path (final rater assignments)")
            yield Input(
                value=str(DEFAULT_OUTPUT),
                id="output_input",
                classes="field-input",
            )
            yield Label("Number of Raters (leave blank if naming each)")
            yield Input(
                value=str(DEFAULT_RATER_COUNT),
                id="rater_count_input",
                classes="field-input",
            )
            yield Label("Explicit Rater Names (comma-separated)")
            yield Input(
                placeholder='e.g., "Ann B, Lena R, Marcus D"',
                id="rater_names_input",
                classes="field-input",
            )
            yield Label("Comparisons Per Rater")
            yield Input(
                value="10",
                id="per_rater_input",
                classes="field-input",
            )
            yield Static("Optimization Settings", classes="bold")
            yield Label("Generated Pairs Output Path (optimizer saves pairs here)")
            yield Input(
                value=str(DEFAULT_PAIRS_OUTPUT),
                id="optimizer_output_input",
                classes="field-input",
            )
            yield Label("Previous Session CSV (optional, for multi-session workflows)")
            yield Input(
                placeholder="e.g., session1_pairs.csv (leave blank for first session)",
                id="previous_csv_input",
                classes="field-input",
            )
            yield Label("Locked Pairs (semicolon-separated: essay_a,essay_b; essay_c,essay_d)")
            yield Input(
                placeholder="e.g., JA24,A1; II24,B1",
                id="locked_pairs_input",
                classes="field-input",
            )
            yield Label("Max Repetitions Per Pair (default: 3)")
            yield Input(
                value="3",
                id="optimizer_max_repeat_input",
                classes="field-input",
            )
            yield Label("Include Anchor-Anchor Comparisons")
            yield Select(
                id="include_anchor_anchor_select",
                options=[("Yes", "yes"), ("No", "no")],
                value="yes",
                classes="field-select",
            )
        with Container(id="actions"):
            yield Button("Generate Assignments (g)", id="generate_button", variant="success")
            yield Button("Reset", id="reset_button")
        yield Static(
            "Load students via CSV (recommended) or comma-separated entry. "
            "Set rater count and comparisons per rater. "
            "Generate Assignments runs the optimizer to create comparison pairs, "
            "then distributes them to raters. Outputs: Pairs CSV + Assignments CSV. "
            "Tip: focus a file path field and drag files onto the terminal to "
            "auto-populate it.",
            id="instructions",
        )
        yield TextLog(id="result", highlight=False)
    yield Footer()


def wrap_log_message(message: str, width: int = MAX_LOG_WIDTH) -> str:
    """Wrap long message to fit within log panel width.

    Args:
        message: Message to wrap
        width: Maximum line width (default: MAX_LOG_WIDTH)

    Returns:
        Wrapped message with newlines inserted
    """
    return textwrap.fill(
        message,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
        subsequent_indent="  ",
    )
