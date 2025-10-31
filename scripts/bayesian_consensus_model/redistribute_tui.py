#!/usr/bin/env python3
"""Textual-based TUI for redistributing CJ comparison pairs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

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
        DynamicSpec,
        OptimizationResult,
        load_dynamic_spec,
        load_previous_comparisons_from_csv,
        optimize_from_dynamic_spec,
        write_design,
    )
    from .redistribute_core import (
        StatusSelector,
        assign_pairs,
        build_rater_list,
        compute_quota_distribution,
        filter_comparisons,
        read_pairs,
        select_comparisons,
        write_assignments,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from scripts.bayesian_consensus_model.d_optimal_workflow import (  # type: ignore[attr-defined]
        OptimizationResult,
        load_dynamic_spec,
        load_previous_comparisons_from_csv,
        optimize_from_dynamic_spec,
        write_design,
    )
    from scripts.bayesian_consensus_model.redistribute_core import (  # type: ignore[attr-defined]
        StatusSelector,
        assign_pairs,
        build_rater_list,
        compute_quota_distribution,
        filter_comparisons,
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


def _load_students_from_csv(csv_path: Path) -> List[str]:
    """Load student IDs from CSV, trying common column names (case-insensitive)."""
    import csv

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        # Build case-insensitive mapping: lowercase → original column name
        fieldname_map = {name.lower(): name for name in reader.fieldnames}

        # Try common column names (case-insensitive)
        for col_name in ["essay_id", "student_id", "id"]:
            if col_name in fieldname_map:
                original_col = fieldname_map[col_name]
                f.seek(0)
                reader = csv.DictReader(f)
                students = [
                    row[original_col].strip()
                    for row in reader
                    if row.get(original_col, "").strip()
                ]
                if not students:
                    raise ValueError(f"CSV column '{original_col}' is empty")
                return students

        raise ValueError(
            f"CSV must have one of: essay_id, student_id, or id column (case-insensitive). "
            f"Found: {', '.join(reader.fieldnames)}"
        )


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
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="panel"):
            yield Label("Redistribute Comparison Pairs", id="title", classes="bold")
            with Vertical(id="form"):
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
                yield Label("Pairs CSV Path (optimized comparison pairs)")
                yield Input(
                    value=str(DEFAULT_OPTIMIZED),
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
                yield Label("Total Comparison Slots")
                yield Input(
                    value="24",
                    id="optimizer_slots_input",
                    placeholder="e.g., 84",
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
                "Generate Assignments runs the optimizer to create comparison pairs, "
                "then distributes them to raters. Outputs: Pairs CSV + Assignments CSV.",
                id="instructions",
            )
            yield TextLog(id="result", highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#students_input", Input).focus()
        self.query_one(TextLog).write("Ready.")

    def action_generate(self) -> None:
        self._generate_assignments()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate_button":
            self._generate_assignments()
        elif event.button.id == "reset_button":
            self._reset_form()

    def _reset_form(self) -> None:
        self.query_one("#students_csv_input", Input).value = ""
        self.query_one("#students_input", Input).value = ""
        self.query_one("#anchors_input", Input).value = ""
        self.query_one("#output_input", Input).value = str(DEFAULT_OUTPUT)
        self.query_one("#rater_count_input", Input).value = str(DEFAULT_RATER_COUNT)
        self.query_one("#rater_names_input", Input).value = ""
        self.query_one("#per_rater_input", Input).value = "10"
        self.query_one("#status_select", Select).value = StatusSelector.ALL.value
        self.query_one("#optimizer_output_input", Input).value = str(DEFAULT_OPTIMIZED)
        self.query_one("#optimizer_slots_input", Input).value = "24"
        self.query_one("#optimizer_max_repeat_input", Input).value = "3"
        self.query_one("#locked_pairs_input", Input).value = ""
        self.query_one("#previous_csv_input", Input).value = ""
        self.query_one("#include_anchor_anchor_select", Select).value = "yes"
        self.query_one(TextLog).write("Form reset.")

    def _generate_assignments(self) -> None:
        log_widget = self.query_one(TextLog)
        log_widget.clear()
        try:
            output_value = self.query_one("#output_input", Input).value.strip()
            if not output_value:
                raise ValueError("Assignments CSV path is required.")
            output_path = Path(output_value)
            if output_path.is_dir():
                raise ValueError("Output path points to a directory; provide a file path.")

            # Always run optimizer first (unified workflow)
            pairs_path = self._run_optimizer(log_widget, clear_log=False)
            if pairs_path is None:
                return

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

            pool = filter_comparisons(comparisons, include_status)
            requested_total = len(names) * per_rater
            available_total = len(pool)

            if available_total == 0:
                raise ValueError(
                    "No comparisons available after filtering. "
                    "Adjust status selection or regenerate pairs."
                )

            shortage = requested_total > available_total
            if shortage:
                quotas = compute_quota_distribution(names, per_rater, available_total)
                total_needed = sum(quotas.values())
                selected = select_comparisons(comparisons, include_status, total_needed)
                assignments = assign_pairs(selected, names, quotas)
            else:
                quotas = {name: per_rater for name in names}
                total_needed = requested_total
                selected = select_comparisons(comparisons, include_status, total_needed)
                assignments = assign_pairs(selected, names, per_rater)
            write_assignments(output_path, assignments)
        except (FileNotFoundError, ValueError) as error:
            log_widget.write(f"[red]Error:[/] {error}")
            return

        actual_counts = [quotas[name] for name in names]
        statuses = ", ".join(sorted({comparison.status for _, comparison in assignments}))
        if shortage:
            log_widget.write(
                f"[yellow]Notice[/]: Requested {requested_total} comparisons but only "
                f"{available_total} available."
            )
        log_widget.write(
            "Success: Generated assignments for "
            f"{len(names)} raters (min {min(actual_counts)}, max {max(actual_counts)})."
        )
        log_widget.write(
            "Total allocated comparisons: "
            f"{sum(actual_counts)} (requested {requested_total})."
        )
        log_widget.write(f"Pairs drawn from statuses: {statuses}")
        log_widget.write(f"Output written to {output_path}")

    def _run_optimizer(self, log_widget: TextLog, *, clear_log: bool) -> Optional[Path]:
        if clear_log:
            log_widget.clear()

        try:
            # Get student IDs - try CSV first, fallback to manual entry
            students_csv = self.query_one("#students_csv_input", Input).value.strip()
            if students_csv:
                csv_path = Path(students_csv)
                if not csv_path.exists():
                    raise FileNotFoundError(f"Students CSV not found: {csv_path}")
                student_list = _load_students_from_csv(csv_path)
                log_widget.write(f"Loaded {len(student_list)} students from CSV")
            else:
                # Fallback to manual comma-separated entry
                students_value = self.query_one("#students_input", Input).value.strip()
                if not students_value:
                    raise ValueError("Provide students via CSV or comma-separated entry.")
                student_list = [s.strip() for s in students_value.split(",") if s.strip()]
                if not student_list:
                    raise ValueError("At least one student essay ID is required.")

            # Get output path
            output_value = self.query_one("#optimizer_output_input", Input).value.strip()
            if not output_value:
                raise ValueError("Optimization output path is required.")

            # Get anchors (optional)
            anchors_value = self.query_one("#anchors_input", Input).value.strip()
            anchor_list = None
            if anchors_value:
                anchor_list = [a.strip() for a in anchors_value.split(",") if a.strip()]

            # Get locked pairs (format: "essay_a,essay_b; essay_c,essay_d" using semicolons between pairs)
            locked_value = self.query_one("#locked_pairs_input", Input).value.strip()
            locked_pairs = None
            if locked_value:
                locked_list = []
                for pair_str in locked_value.split(";"):  # Semicolon separates multiple pairs
                    pair_str = pair_str.strip()
                    if not pair_str:
                        continue
                    parts = [p.strip() for p in pair_str.split(",")]  # Comma within pair
                    if len(parts) == 2:
                        locked_list.append((parts[0], parts[1]))
                    elif pair_str:  # Non-empty but wrong format
                        raise ValueError(f"Invalid locked pair format: '{pair_str}' (use 'essay_a,essay_b')")
                locked_pairs = locked_list if locked_list else None

            # Get total slots
            slots_raw = self.query_one("#optimizer_slots_input", Input).value.strip()
            if not slots_raw:
                raise ValueError("Total slots is required for optimization.")
            total_slots = int(slots_raw)

            # Get max repeat
            max_repeat_raw = self.query_one("#optimizer_max_repeat_input", Input).value.strip()
            max_repeat = int(max_repeat_raw) if max_repeat_raw else 3
            if max_repeat <= 0:
                raise ValueError("Optimization max repeat must be positive.")

            # Get include anchor-anchor toggle
            include_aa_value = self.query_one("#include_anchor_anchor_select", Select).value
            include_anchor_anchor = include_aa_value == "yes"

            # Get previous comparisons CSV (optional, for multi-session workflows)
            previous_csv_value = self.query_one("#previous_csv_input", Input).value.strip()
            previous_comparisons = None
            if previous_csv_value:
                previous_csv_path = Path(previous_csv_value)
                previous_comparisons = load_previous_comparisons_from_csv(previous_csv_path)
                log_widget.write(f"Loaded {len(previous_comparisons)} previous comparisons")

            # Build dynamic spec
            spec = load_dynamic_spec(
                students=student_list,
                anchors=anchor_list,
                include_anchor_anchor=include_anchor_anchor,
                previous_comparisons=previous_comparisons,
                locked_pairs=locked_pairs,
                total_slots=total_slots,
            )

            # Run optimizer
            result = optimize_from_dynamic_spec(spec, max_repeat=max_repeat)

            # Write output
            output_path = Path(output_value)
            write_design(result.optimized_design, output_path)
            self.query_one("#students_input", Input).value = students_value

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
        log_widget.write(
            "Minimum required slots: "
            f"{result.min_slots_required} "
            f"(anchor adjacency {result.anchor_adjacency_count}, "
            f"baseline-required {result.required_pair_count})"
        )

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
