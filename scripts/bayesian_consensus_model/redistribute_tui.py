#!/usr/bin/env python3
"""Textual-based TUI for redistributing CJ comparison pairs."""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button, Input, Select

try:
    from textual.widgets import TextLog  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - compatibility with older Textual
    from textual.widgets import Log as TextLog  # type: ignore

from scripts.bayesian_consensus_model.tui.file_drop_handler import (
    FILE_DROP_TARGET_IDS,
    extract_paths_from_paste,
    unquote_file_path,
)
from scripts.bayesian_consensus_model.tui.form_layout import (
    APP_CSS,
    DEFAULT_OUTPUT,
    DEFAULT_PAIRS_OUTPUT,
    DEFAULT_RATER_COUNT,
    create_form_layout,
    wrap_log_message,
)
from scripts.bayesian_consensus_model.tui.result_formatter import (
    format_assignment_summary,
    format_optimization_summary,
)
from scripts.bayesian_consensus_model.tui.workflow_executor import (
    extract_assignment_inputs,
    extract_optimizer_inputs,
    generate_assignments,
    run_optimizer,
)


class RedistributeApp(App):
    """Interactive TUI for generating rater assignments."""

    TITLE = "CJ Pair Generator"
    CSS = APP_CSS

    BINDINGS = [
        Binding("g", "generate", "Generate assignments"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create the form layout."""
        yield from create_form_layout()

    def on_mount(self) -> None:
        """Initialize app state on mount."""
        self.query_one("#students_input", Input).focus()
        self.query_one(TextLog).write("Ready.")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Remove quotes from file paths set by Finder drag-and-drop."""
        if event.input.id not in FILE_DROP_TARGET_IDS:
            return

        unquoted = unquote_file_path(event.input.value)
        if unquoted:
            event.input.value = unquoted

    def on_paste(self, event: events.Paste) -> None:
        """Handle pasted file paths in file drop target fields."""
        file_paths = extract_paths_from_paste(event.text)
        if not file_paths:
            super().on_paste(event)
            return

        event.prevent_default()
        event.stop()

        # Target the focused input if it's a file drop target
        focused = self.focused
        if isinstance(focused, Input) and focused.id in FILE_DROP_TARGET_IDS:
            target_input = focused
        else:
            target_input = self.query_one("#students_csv_input", Input)

        target_input.value = ", ".join(file_paths)

        # Show confirmation
        log_widget = self.query_one(TextLog)
        placeholder = target_input.placeholder or target_input.id.replace("_", " ")
        summary_path = file_paths[0]
        if len(file_paths) > 1:
            summary_path += f" (+{len(file_paths) - 1} more)"
        log_widget.write(
            wrap_log_message(
                f"Detected file drop; populated '{placeholder}' with {summary_path}."
            )
        )

    def action_generate(self) -> None:
        """Generate assignments (keyboard shortcut handler)."""
        self._generate_assignments()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "generate_button":
            self._generate_assignments()
        elif event.button.id == "reset_button":
            self._reset_form()

    def _reset_form(self) -> None:
        """Reset all form fields to defaults."""
        self.query_one("#students_csv_input", Input).value = ""
        self.query_one("#students_input", Input).value = ""
        self.query_one("#anchors_input", Input).value = ""
        self.query_one("#output_input", Input).value = str(DEFAULT_OUTPUT)
        self.query_one("#rater_count_input", Input).value = str(DEFAULT_RATER_COUNT)
        self.query_one("#rater_names_input", Input).value = ""
        self.query_one("#per_rater_input", Input).value = "10"
        self.query_one("#optimizer_output_input", Input).value = str(DEFAULT_PAIRS_OUTPUT)
        self.query_one("#optimizer_max_repeat_input", Input).value = "3"
        self.query_one("#locked_pairs_input", Input).value = ""
        self.query_one("#previous_csv_input", Input).value = ""
        self.query_one("#include_anchor_anchor_select", Select).value = "yes"
        self.query_one(TextLog).write("Form reset.")

    def _generate_assignments(self) -> None:
        """Run optimizer and generate assignments workflow."""
        log_widget = self.query_one(TextLog)
        log_widget.clear()

        try:
            # Extract form inputs
            optimizer_inputs = extract_optimizer_inputs(self.query_one)
            assignment_inputs = extract_assignment_inputs(self.query_one)

            # Run optimizer
            opt_result, pairs_path, students_value = run_optimizer(optimizer_inputs)

            # Log optimizer results
            log_widget.write(wrap_log_message(f"Loaded {len(opt_result.students)} students"))
            log_widget.write(
                wrap_log_message(
                    f"Generating {opt_result.total_comparisons} pairs for "
                    f"{len(opt_result.students)} students"
                )
            )
            if optimizer_inputs.previous_csv:
                prev_count = len(opt_result.baseline_design)
                log_widget.write(
                    wrap_log_message(f"Loaded {prev_count} previous comparisons")
                )

            for message in format_optimization_summary(opt_result, pairs_path):
                log_widget.write(wrap_log_message(message))

            # Update students display field
            self.query_one("#students_input", Input).value = students_value

            # Generate assignments
            assignment_result = generate_assignments(assignment_inputs, pairs_path)

            # Log assignment results
            for message in format_assignment_summary(
                assignment_result.quotas,
                assignment_result.requested_total,
                assignment_result.available_total,
                assignment_result.output_path,
            ):
                log_widget.write(wrap_log_message(message))

        except (FileNotFoundError, ValueError) as error:
            log_widget.write(wrap_log_message(f"[red]Error:[/] {error}"))


if __name__ == "__main__":
    RedistributeApp().run()
