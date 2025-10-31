#!/usr/bin/env python3
"""Textual-based TUI for redistributing CJ comparison pairs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

try:
    from textual.widgets import TextLog  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - compatibility with older Textual
    from textual.widgets import Log as TextLog  # type: ignore

try:
    from .d_optimal_workflow import (  # type: ignore[attr-defined]
        DEFAULT_ANCHOR_ORDER,
        OptimizationResult,
        optimize_schedule,
        write_design,
    )
    from .redistribute_core import (
        StatusSelector,
        assign_pairs,
        build_rater_list,
        read_pairs,
        select_comparisons,
        write_assignments,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from scripts.bayesian_consensus_model.d_optimal_workflow import (  # type: ignore[attr-defined]
        DEFAULT_ANCHOR_ORDER,
        OptimizationResult,
        optimize_schedule,
        write_design,
    )
    from scripts.bayesian_consensus_model.redistribute_core import (  # type: ignore[attr-defined]
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
DEFAULT_OPTIMIZED = Path(
    "scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs_optimized.csv"
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
        height: 28;
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
        Binding("o", "optimize", "Optimize pairs"),
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
                yield Static("Optimization Settings", classes="bold")
                yield Label("Optimization Output CSV Path")
                yield Input(
                    value=str(DEFAULT_OPTIMIZED),
                    id="optimizer_output_input",
                    classes="field-input",
                )
                yield Label("Optimization Status Pool")
                yield Select(
                    id="optimizer_status_select",
                    options=[
                        ("Core only", StatusSelector.CORE.value),
                        ("Core + extra", StatusSelector.ALL.value),
                    ],
                    value=StatusSelector.CORE.value,
                    classes="field-select",
                )
                yield Label("Optimization Total Slots (blank = baseline count)")
                yield Input(
                    id="optimizer_slots_input",
                    placeholder="e.g., 84",
                    classes="field-input",
                )
                yield Label("Optimization Max Repeat")
                yield Input(
                    value="3",
                    id="optimizer_max_repeat_input",
                    classes="field-input",
                )
                yield Label("Optimize before assigning?")
                yield Select(
                    id="optimizer_toggle",
                    options=[("No", "no"), ("Yes", "yes")],
                    value="no",
                    classes="field-select",
                )
            with Container(id="actions"):
                yield Button("Optimize (o)", id="optimize_button", variant="primary")
                yield Button("Generate (g)", id="generate_button", variant="success")
                yield Button("Reset", id="reset_button")
            yield Static(
                "Use Optimize (o) to generate a refreshed schedule, or toggle automatic optimization before assignment. "
                "Provide either the rater count or explicit names before generating assignments.",
                id="instructions",
            )
            yield TextLog(id="result", highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pairs_input", Input).focus()
        self.query_one(TextLog).write("Ready.")

    def action_generate(self) -> None:
        self._generate_assignments()

    def action_optimize(self) -> None:
        log_widget = self.query_one(TextLog)
        self._run_optimizer(log_widget, clear_log=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate_button":
            self._generate_assignments()
        elif event.button.id == "optimize_button":
            self.action_optimize()
        elif event.button.id == "reset_button":
            self._reset_form()

    def _reset_form(self) -> None:
        self.query_one("#pairs_input", Input).value = str(DEFAULT_PAIRS)
        self.query_one("#output_input", Input).value = str(DEFAULT_OUTPUT)
        self.query_one("#rater_count_input", Input).value = str(DEFAULT_RATER_COUNT)
        self.query_one("#rater_names_input", Input).value = ""
        self.query_one("#per_rater_input", Input).value = "10"
        self.query_one("#status_select", Select).value = StatusSelector.ALL.value
        self.query_one("#optimizer_output_input", Input).value = str(DEFAULT_OPTIMIZED)
        self.query_one("#optimizer_status_select", Select).value = StatusSelector.CORE.value
        self.query_one("#optimizer_slots_input", Input).value = ""
        self.query_one("#optimizer_max_repeat_input", Input).value = "3"
        self.query_one("#optimizer_toggle", Select).value = "no"
        self.query_one(TextLog).write("Form reset.")

    def _generate_assignments(self) -> None:
        log_widget = self.query_one(TextLog)
        log_widget.clear()
        try:
            pairs_value = self.query_one("#pairs_input", Input).value.strip()
            if not pairs_value:
                raise ValueError("Pairs CSV path is required.")
            output_value = self.query_one("#output_input", Input).value.strip()
            if not output_value:
                raise ValueError("Output CSV path is required.")
            output_path = Path(output_value)
            if output_path.is_dir():
                raise ValueError("Output path points to a directory; provide a file path.")

            if self.query_one("#optimizer_toggle", Select).value == "yes":
                optimized_path = self._run_optimizer(log_widget, clear_log=False)
                if optimized_path is None:
                    return
                pairs_path = optimized_path
            else:
                pairs_path = Path(pairs_value)

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

    def _run_optimizer(self, log_widget: TextLog, *, clear_log: bool) -> Optional[Path]:
        if clear_log:
            log_widget.clear()

        try:
            pairs_value = self.query_one("#pairs_input", Input).value.strip()
            if not pairs_value:
                raise ValueError("Pairs CSV path is required for optimization.")
            output_value = self.query_one("#optimizer_output_input", Input).value.strip()
            if not output_value:
                raise ValueError("Optimization output path is required.")

            slots_raw = self.query_one("#optimizer_slots_input", Input).value.strip()
            total_slots = int(slots_raw) if slots_raw else None

            max_repeat_raw = self.query_one("#optimizer_max_repeat_input", Input).value.strip()
            max_repeat = int(max_repeat_raw) if max_repeat_raw else 3
            if max_repeat <= 0:
                raise ValueError("Optimization max repeat must be positive.")

            status_value = self.query_one("#optimizer_status_select", Select).value
            include_status = StatusSelector(status_value or StatusSelector.CORE.value)
            status_filter = None if include_status is StatusSelector.ALL else (include_status.value,)

            result = optimize_schedule(
                Path(pairs_value),
                total_slots=total_slots,
                max_repeat=max_repeat,
                anchor_order=DEFAULT_ANCHOR_ORDER,
                status_filter=status_filter,
            )

            output_path = Path(output_value)
            write_design(result.optimized_design, output_path)
            self.query_one("#pairs_input", Input).value = str(output_path)

            self._log_optimizer_summary(log_widget, result, output_path)
            return output_path
        except ValueError as exc:
            log_widget.write(f"[red]Optimization error:[/] {exc}")
        except FileNotFoundError as exc:
            log_widget.write(f"[red]Optimization error:[/] {exc}")
        return None

    def _log_optimizer_summary(
        self,
        log_widget: TextLog,
        result: OptimizationResult,
        output_path: Path,
    ) -> None:
        log_widget.write(
            "[green]Optimization succeeded[/]: "
            f"log-det gain {result.log_det_gain:.4f} "
            f"({result.baseline_log_det:.4f} → {result.optimized_log_det:.4f})"
        )
        log_widget.write(f"Optimized schedule written to {output_path}")

        log_widget.write("Type distribution (optimized):")
        for comp_type, count in result.optimized_diagnostics.type_counts.items():
            log_widget.write(f"  {comp_type:<16} {count}")

        coverage = result.optimized_diagnostics.student_anchor_coverage
        if coverage:
            log_widget.write("Student anchor coverage:")
            for student in sorted(coverage):
                anchors = ", ".join(coverage[student]) or "—"
                log_widget.write(f"  {student:<10} {anchors}")
        else:
            log_widget.write("Student anchor coverage: none")

        missing = sorted(set(result.students) - set(coverage))
        if missing:
            log_widget.write(
                "[yellow]Warning[/]: Missing anchor coverage for "
                + ", ".join(missing)
            )

        repeats = result.optimized_diagnostics.repeat_counts
        if repeats:
            log_widget.write("Repeated pairs (>1 occurrence):")
            for key, count in sorted(repeats.items()):
                log_widget.write(f"  {key}: {count}×")
        else:
            log_widget.write("Repeated pairs: none")


if __name__ == "__main__":
    RedistributeApp().run()
