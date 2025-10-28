#!/usr/bin/env python3
"""Textual-based TUI for redistributing CJ comparison pairs."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

try:
    from textual.widgets import TextLog  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - compatibility with older Textual
    from textual.widgets import Log as TextLog  # type: ignore

try:
    from .redistribute_core import (
        StatusSelector,
        assign_pairs,
        build_rater_list,
        read_pairs,
        select_comparisons,
        write_assignments,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from redistribute_core import (  # type: ignore
        StatusSelector,
        assign_pairs,
        build_rater_list,
        read_pairs,
        select_comparisons,
        write_assignments,
    )

DEFAULT_PAIRS = Path(
    "scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs.csv"
)
DEFAULT_OUTPUT = Path("session2_dynamic_assignments.csv")
DEFAULT_RATER_COUNT = 14


class RedistributeApp(App):
    """Interactive TUI for generating rater assignments."""

    CSS = """
    Screen {
        overflow-y: auto;
        align: center top;
    }

    #panel {
        width: 80%;
        max-width: 90;
        border: round $accent;
        padding: 1 2;
        background: $boost;
    }

    .field-input {
        margin-bottom: 1;
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
        border: solid $accent;
    }

    .field-select {
        margin-bottom: 1;
        height: 3;
        background: $surface-lighten-1;
        border: solid $accent;
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
        height: 22;
        overflow-y: auto;
    }

    #result {
        height: 5;
        margin-top: 1;
    }

    #actions {
        layout: horizontal;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("g", "generate", "Generate assignments"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="panel"):
            yield Label("Redistribute Comparison Pairs", id="title", classes="bold")
            with Vertical(id="form"):
                yield Label("Pairs CSV Path")
                yield Input(
                    value=str(DEFAULT_PAIRS),
                    id="pairs_input",
                    classes="field-input",
                )
                yield Label("Output CSV Path")
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
                yield Label("Include Comparison Statuses")
                yield Select(
                    id="status_select",
                    options=[
                        ("Core only", StatusSelector.CORE.value),
                        ("Core + extra", StatusSelector.ALL.value),
                    ],
                    value=StatusSelector.ALL.value,
                    classes="field-select",
                )
            with Container(id="actions"):
                yield Button("Generate (g)", id="generate_button", variant="success")
                yield Button("Reset", id="reset_button")
            yield Static(
                "Enter either the total number of raters or a comma-separated list of names. "
                "Adjust comparisons per rater and press g to generate assignments.",
                id="instructions",
            )
            yield TextLog(id="result", highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pairs_input", Input).focus()
        self.query_one(TextLog).write("Ready.")

    def action_generate(self) -> None:
        self._generate_assignments()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate_button":
            self._generate_assignments()
        elif event.button.id == "reset_button":
            self._reset_form()

    def _reset_form(self) -> None:
        self.query_one("#pairs_input", Input).value = str(DEFAULT_PAIRS)
        self.query_one("#output_input", Input).value = str(DEFAULT_OUTPUT)
        self.query_one("#rater_count_input", Input).value = str(DEFAULT_RATER_COUNT)
        self.query_one("#rater_names_input", Input).value = ""
        self.query_one("#per_rater_input", Input).value = "10"
        self.query_one("#status_select", Select).value = StatusSelector.ALL.value
        self.query_one(TextLog).write("Form reset.")

    def _generate_assignments(self) -> None:
        log_widget = self.query_one(TextLog)
        log_widget.clear()
        try:
            pairs_path = Path(self.query_one("#pairs_input", Input).value.strip())
            output_path = Path(self.query_one("#output_input", Input).value.strip())
            if not pairs_path:
                raise ValueError("Pairs CSV path is required.")
            if output_path.is_dir():
                raise ValueError("Output path points to a directory; provide a file path.")

            comparisons = read_pairs(pairs_path)

            names_raw = self.query_one("#rater_names_input", Input).value.strip()
            count_raw = self.query_one("#rater_count_input", Input).value.strip()
            per_rater_raw = self.query_one("#per_rater_input", Input).value.strip()
            status_value = self.query_one("#status_select", Select).value
            include_status = StatusSelector(status_value or StatusSelector.ALL.value)

            per_rater = int(per_rater_raw) if per_rater_raw else 10
            if per_rater <= 0:
                raise ValueError("Comparisons per rater must be positive.")

            if names_raw:
                names = build_rater_list(None, [names_raw])
            else:
                if not count_raw:
                    raise ValueError("Provide a rater count or explicit rater names.")
                try:
                    count = int(count_raw)
                except ValueError as exc:
                    raise ValueError("Rater count must be an integer.") from exc
                names = build_rater_list(count, None)

            total_needed = len(names) * per_rater
            selected = select_comparisons(comparisons, include_status, total_needed)
            assignments = assign_pairs(selected, names, per_rater)
            write_assignments(output_path, assignments)
        except (FileNotFoundError, ValueError) as error:
            log_widget.write(f"[red]Error:[/] {error}")
            return

        statuses = ", ".join(sorted({comparison.status for _, comparison in assignments}))
        log_widget.write(
            f"Success: Generated assignments for {len(names)} raters "
            f"({per_rater} comparisons each)."
        )
        log_widget.write(f"Pairs drawn from statuses: {statuses}")
        log_widget.write(f"Output written to {output_path}")


if __name__ == "__main__":
    RedistributeApp().run()
