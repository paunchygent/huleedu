"""Rich output formatting for model checker CLI.

This module provides Rich-based formatting functions for displaying
model comparison results in the CLI.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)

console = Console()


def format_model_status(
    discovered: DiscoveredModel | None,
    in_manifest: bool,
    is_new: bool,
    is_deprecated: bool,
    is_updated: bool,
) -> tuple[str, str]:
    """Format model status with emoji and description.

    Args:
        discovered: Discovered model (None if only in manifest)
        in_manifest: Whether model is in manifest
        is_new: Whether model is newly discovered
        is_deprecated: Whether model is deprecated
        is_updated: Whether model metadata changed

    Returns:
        Tuple of (emoji, description)
    """
    if is_deprecated:
        return "🗑️", "Deprecated"
    elif is_new:
        return "🆕", "New"
    elif is_updated:
        return "⚠️", "Updated"
    elif in_manifest:
        return "✅", "Current"
    else:
        return "❓", "Unknown"


def format_comparison_table(result: ModelComparisonResult, verbose: bool = False) -> Table:
    """Format comparison result as Rich table with family-aware sections.

    Displays models in two priority sections:
    1. Tracked Family Updates: New variants in actively tracked families (actionable)
    2. Untracked Families: Models from families not currently tracked (informational)

    Args:
        result: Comparison result to format
        verbose: Whether to include detailed metadata

    Returns:
        Rich Table with two sections: tracked families and untracked families
    """
    table = Table(
        title=f"[bold]{result.provider.value.upper()}[/bold] Models",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Status", style="dim", width=12)
    table.add_column("Model ID", style="cyan")
    table.add_column("Display Name", style="white")

    if verbose:
        table.add_column("API Version", style="yellow")
        table.add_column("Max Tokens", style="green", justify="right")
        table.add_column("Capabilities", style="magenta")

    # Track which models we've seen
    seen_model_ids: set[str] = set()

    # Section 1: Tracked Family Updates (actionable)
    if result.new_models_in_tracked_families:
        table.add_row("[bold yellow]Tracked Family Updates[/bold yellow]", "", "", *[""] * (3 if verbose else 0))
        for model in result.new_models_in_tracked_families:
            seen_model_ids.add(model.model_id)
            row = ["🔄 In-family", model.model_id, model.display_name]

            if verbose:
                api_ver = model.api_version or "N/A"
                max_tok = str(model.max_tokens) if model.max_tokens else "N/A"
                caps = ", ".join(model.capabilities[:3]) if model.capabilities else "N/A"
                row.extend([api_ver, max_tok, caps])

            table.add_row(*row)

    # Section 2: Untracked Families (informational)
    if result.new_untracked_families:
        if result.new_models_in_tracked_families:
            # Add separator row if we already had tracked family updates
            table.add_row("", "", "", *[""] * (3 if verbose else 0))
        table.add_row("[bold blue]Untracked Families (Informational)[/bold blue]", "", "", *[""] * (3 if verbose else 0))
        for model in result.new_untracked_families:
            seen_model_ids.add(model.model_id)
            row = ["ℹ️  Untracked", model.model_id, model.display_name]

            if verbose:
                api_ver = model.api_version or "N/A"
                max_tok = str(model.max_tokens) if model.max_tokens else "N/A"
                caps = ", ".join(model.capabilities[:3]) if model.capabilities else "N/A"
                row.extend([api_ver, max_tok, caps])

            table.add_row(*row)

    # Add updated models
    if result.updated_models:
        if result.new_models_in_tracked_families or result.new_untracked_families:
            table.add_row("", "", "", *[""] * (3 if verbose else 0))
        table.add_row("[bold]Updated Models[/bold]", "", "", *[""] * (3 if verbose else 0))
        for model_id, discovered in result.updated_models:
            seen_model_ids.add(model_id)
            row = ["⚠️  Updated", model_id, discovered.display_name]

            if verbose:
                api_ver = discovered.api_version or "N/A"
                max_tok = str(discovered.max_tokens) if discovered.max_tokens else "N/A"
                caps = ", ".join(discovered.capabilities[:3]) if discovered.capabilities else "N/A"
                row.extend([api_ver, max_tok, caps])

            table.add_row(*row)

    # Add deprecated models
    if result.deprecated_models:
        if result.new_models_in_tracked_families or result.new_untracked_families or result.updated_models:
            table.add_row("", "", "", *[""] * (3 if verbose else 0))
        table.add_row("[bold]Deprecated Models[/bold]", "", "", *[""] * (3 if verbose else 0))
        for model_id in result.deprecated_models:
            if model_id not in seen_model_ids:
                seen_model_ids.add(model_id)
                row = ["🗑️  Deprecated", model_id, "N/A"]

                if verbose:
                    row.extend(["N/A", "N/A", "N/A"])

                table.add_row(*row)

    return table


def format_summary(results: list[ModelComparisonResult]) -> None:
    """Print summary of all comparison results with family-aware counts.

    Args:
        results: List of comparison results
    """
    console.print("\n[bold]Summary[/bold]")
    console.print("=" * 50)

    total_in_family = sum(len(r.new_models_in_tracked_families) for r in results)
    total_untracked = sum(len(r.new_untracked_families) for r in results)
    total_updated = sum(len(r.updated_models) for r in results)
    total_deprecated = sum(len(r.deprecated_models) for r in results)
    total_breaking = sum(len(r.breaking_changes) for r in results)

    console.print(f"🔄 In-family updates: {total_in_family}")
    console.print(f"ℹ️  Untracked families: {total_untracked}")
    console.print(f"⚠️  Updated models: {total_updated}")
    console.print(f"🗑️  Deprecated models: {total_deprecated}")
    console.print(f"⛔ Breaking changes: {total_breaking}")

    providers_up_to_date = [r.provider.value for r in results if r.is_up_to_date]
    if providers_up_to_date:
        console.print(f"\n✅ Up-to-date providers: {', '.join(providers_up_to_date)}")


def format_breaking_changes(results: list[ModelComparisonResult]) -> None:
    """Format and display breaking changes if any.

    Args:
        results: List of comparison results
    """
    all_breaking: list[tuple[str, str]] = []
    for result in results:
        for change in result.breaking_changes:
            all_breaking.append((result.provider.value, change))

    if not all_breaking:
        return

    panel_content = "\n".join(
        [f"• [{provider.upper()}] {change}" for provider, change in all_breaking]
    )

    panel = Panel(
        panel_content,
        title="[bold red]⛔ Breaking Changes Detected[/bold red]",
        border_style="red",
    )

    console.print("\n")
    console.print(panel)
