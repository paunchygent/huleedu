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
    """Format comparison result as Rich table.

    Args:
        result: Comparison result to format
        verbose: Whether to include detailed metadata

    Returns:
        Rich Table with comparison data
    """
    table = Table(
        title=f"[bold]{result.provider.value.upper()}[/bold] Models",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Status", style="dim", width=8)
    table.add_column("Model ID", style="cyan")
    table.add_column("Display Name", style="white")

    if verbose:
        table.add_column("API Version", style="yellow")
        table.add_column("Max Tokens", style="green", justify="right")
        table.add_column("Capabilities", style="magenta")

    # Track which models we've seen
    seen_model_ids: set[str] = set()

    # Add new models
    for model in result.new_models:
        seen_model_ids.add(model.model_id)
        emoji, status = format_model_status(
            discovered=model,
            in_manifest=False,
            is_new=True,
            is_deprecated=False,
            is_updated=False,
        )

        row = [f"{emoji} {status}", model.model_id, model.display_name]

        if verbose:
            api_ver = model.api_version or "N/A"
            max_tok = str(model.max_tokens) if model.max_tokens else "N/A"
            caps = ", ".join(model.capabilities[:3]) if model.capabilities else "N/A"
            row.extend([api_ver, max_tok, caps])

        table.add_row(*row)

    # Add updated models
    for model_id, discovered in result.updated_models:
        seen_model_ids.add(model_id)
        emoji, status = format_model_status(
            discovered=discovered,
            in_manifest=True,
            is_new=False,
            is_deprecated=False,
            is_updated=True,
        )

        row = [f"{emoji} {status}", model_id, discovered.display_name]

        if verbose:
            api_ver = discovered.api_version or "N/A"
            max_tok = str(discovered.max_tokens) if discovered.max_tokens else "N/A"
            caps = ", ".join(discovered.capabilities[:3]) if discovered.capabilities else "N/A"
            row.extend([api_ver, max_tok, caps])

        table.add_row(*row)

    # Add deprecated models
    for model_id in result.deprecated_models:
        if model_id not in seen_model_ids:
            seen_model_ids.add(model_id)
            emoji, status = format_model_status(
                discovered=None,
                in_manifest=True,
                is_new=False,
                is_deprecated=True,
                is_updated=False,
            )

            row = [f"{emoji} {status}", model_id, "N/A"]

            if verbose:
                row.extend(["N/A", "N/A", "N/A"])

            table.add_row(*row)

    return table


def format_summary(results: list[ModelComparisonResult]) -> None:
    """Print summary of all comparison results.

    Args:
        results: List of comparison results
    """
    console.print("\n[bold]Summary[/bold]")
    console.print("=" * 50)

    total_new = sum(len(r.new_models) for r in results)
    total_deprecated = sum(len(r.deprecated_models) for r in results)
    total_updated = sum(len(r.updated_models) for r in results)
    total_breaking = sum(len(r.breaking_changes) for r in results)

    console.print(f"🆕 New models: {total_new}")
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
