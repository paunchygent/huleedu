#!/usr/bin/env python3
"""Textual-based TUI for redistributing CJ comparison pairs."""

from __future__ import annotations

from pathlib import Path

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button, Input, Select

try:
    from textual.widgets import RichLog as TextLog  # type: ignore[attr-defined]
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
)
from scripts.bayesian_consensus_model.tui.help_screen import HelpScreen
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
        Binding("f1", "show_help", "Help", priority=True),
        Binding("question_mark", "show_help", show=False, priority=True),
        Binding("g", "generate", "Generate assignments"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create the form layout."""
        yield from create_form_layout()

    def on_mount(self) -> None:
        """Initialize app state on mount."""
        log_widget = self.query_one(TextLog)
        log_widget.write("Initializing CJ Pair Generator...")
        self.query_one("#students_csv_input", Input).focus()
        log_widget.write("Ready.")

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
        log_widget.write(f"Detected file drop; populated '{placeholder}' with {summary_path}.")

    def action_show_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_generate(self) -> None:
        """Generate assignments (keyboard shortcut handler)."""
        self.query_one("#generate_button", Button).disabled = True
        self._generate_assignments()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "generate_button":
            event.button.disabled = True
            self._generate_assignments()
        elif event.button.id == "reset_button":
            self._reset_form()
        elif event.button.id in self._BROWSE_BUTTON_CONFIG:
            field_id, title, mode = self._BROWSE_BUTTON_CONFIG[event.button.id]
            input_widget = self.query_one(f"#{field_id}", Input)
            current_value = input_widget.value.strip()
            placeholder = input_widget.placeholder or field_id.replace("_", " ")
            self._launch_file_dialog(field_id, title, current_value, placeholder, mode)

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

    @work(thread=True, exclusive=True, exit_on_error=False)
    async def _generate_assignments(self) -> None:
        """Run optimizer and generate assignments workflow in background thread."""
        log_widget = self.query_one(TextLog)
        self.call_from_thread(log_widget.clear)

        try:
            # Extract form inputs
            self.call_from_thread(log_widget.write, "Extracting form inputs...")
            optimizer_inputs = extract_optimizer_inputs(self.query_one)
            assignment_inputs = extract_assignment_inputs(self.query_one)

            # Run optimizer
            self.call_from_thread(log_widget.write, "Running D-optimal optimizer...")
            opt_result, pairs_path, students_value = run_optimizer(optimizer_inputs)

            # Log optimizer results
            self.call_from_thread(log_widget.write, f"Loaded {len(opt_result.students)} students")
            self.call_from_thread(
                log_widget.write,
                f"Generating {opt_result.total_comparisons} pairs for "
                f"{len(opt_result.students)} students",
            )
            if optimizer_inputs.previous_csv:
                prev_count = len(opt_result.baseline_design)
                self.call_from_thread(
                    log_widget.write,
                    f"Loaded {prev_count} previous comparisons",
                )

            for message in format_optimization_summary(opt_result, pairs_path):
                self.call_from_thread(log_widget.write, message)

            # Update students display field
            def update_students_field(value: str) -> None:
                self.query_one("#students_input", Input).value = value

            self.call_from_thread(update_students_field, students_value)

            # Generate assignments
            self.call_from_thread(log_widget.write, "Generating rater assignments...")
            assignment_result = generate_assignments(assignment_inputs, pairs_path)

            # Log assignment results
            for message in format_assignment_summary(
                assignment_result.quotas,
                assignment_result.requested_total,
                assignment_result.available_total,
                assignment_result.output_path,
            ):
                self.call_from_thread(log_widget.write, message)

            self.call_from_thread(log_widget.write, "[green]Complete![/]")

        except (FileNotFoundError, ValueError) as error:
            self.call_from_thread(log_widget.write, f"[red]Error:[/] {error}")
        finally:
            # Re-enable button in main thread
            def enable_button() -> None:
                self.query_one("#generate_button", Button).disabled = False

            self.call_from_thread(enable_button)

    _BROWSE_BUTTON_CONFIG: dict[str, tuple[str, str, str]] = {
        "output_browse_button": (
            "output_input",
            "Save assignments CSV",
            "save",
        ),
        "optimizer_output_browse_button": (
            "optimizer_output_input",
            "Save comparison pairs CSV",
            "save",
        ),
        "students_csv_browse_button": (
            "students_csv_input",
            "Select students CSV",
            "open",
        ),
        "previous_csv_browse_button": (
            "previous_csv_input",
            "Select previous session CSV",
            "open",
        ),
    }

    @work(thread=True, exclusive=False, exit_on_error=False)
    async def _launch_file_dialog(
        self,
        field_id: str,
        title: str,
        current_value: str,
        placeholder: str,
        mode: str,
    ) -> None:
        """Open a native file dialog and update the target input field."""
        log_widget = self.query_one(TextLog)

        try:
            from crossfiledialog import exceptions, open_file, save_file
        except ImportError as exc:  # pragma: no cover - package missing
            self.call_from_thread(
                log_widget.write,
                f"[red]File dialog error:[/] crossfiledialog unavailable ({exc})",
            )
            return

        start_dir = self._derive_start_dir(current_value)
        try:
            if mode == "save":
                result = save_file(title=title, start_dir=start_dir)
            else:
                result = open_file(title=title, start_dir=start_dir)
        except exceptions.NoImplementationFoundException:
            self.call_from_thread(
                log_widget.write,
                "[yellow]Notice[/]: Native file dialogs are not supported on this platform.",
            )
            return
        except Exception as exc:  # pragma: no cover - OS dialog failure
            self.call_from_thread(log_widget.write, f"[red]File dialog error:[/] {exc}")
            return

        if not result:
            self.call_from_thread(log_widget.write, f"No changes made to {placeholder} path.")
            return

        resolved_path = str(Path(result).expanduser())

        def update_field() -> None:
            target_input = self.query_one(f"#{field_id}", Input)
            target_input.value = resolved_path
            target_input.focus()

        self.call_from_thread(update_field)
        self.call_from_thread(
            log_widget.write,
            f"Updated {placeholder} path to {resolved_path}",
        )

    @staticmethod
    def _derive_start_dir(current_value: str) -> str | None:
        """Determine a sensible starting directory for native file dialogs."""
        if not current_value:
            return None

        try:
            candidate = Path(current_value).expanduser()
        except (OSError, ValueError):
            return None

        if candidate.is_dir():
            return str(candidate)

        parent = candidate.parent
        if parent.exists():
            return str(parent)

        return None


def main() -> None:
    """Entry point for standalone executable."""
    RedistributeApp().run()


if __name__ == "__main__":
    main()
