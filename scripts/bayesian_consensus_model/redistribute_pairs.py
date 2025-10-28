#!/usr/bin/env python3
"""Typer CLI wrapper for comparison pair redistribution."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

try:
    from .redistribute_core import (
        Comparison,
        StatusSelector,
        assign_pairs,
        build_rater_list,
        read_pairs,
        select_comparisons,
        write_assignments,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from redistribute_core import (  # type: ignore
        Comparison,
        StatusSelector,
        assign_pairs,
        build_rater_list,
        read_pairs,
        select_comparisons,
        write_assignments,
    )

app = typer.Typer(help="Redistribute CJ comparison pairs across available raters.")


def _resolve_raters(
    raters: Optional[int],
    rater_names: Optional[List[str]],
) -> List[str]:
    if rater_names:
        return build_rater_list(None, rater_names)

    if raters is None:
        raise ValueError("Provide --raters or specify --rater-name options.")
    return build_rater_list(raters, None)


@app.command()
def redistribute(
    pairs_csv: Optional[Path] = typer.Option(
        None,
        "--pairs-csv",
        metavar="PATH",
        help="Path to the comparison pairs CSV (e.g. session2_pairs.csv).",
    ),
    output_csv: Optional[Path] = typer.Option(
        None,
        "--output-csv",
        metavar="PATH",
        help="Destination CSV for the generated assignments.",
    ),
    raters: Optional[int] = typer.Option(
        None,
        "--raters",
        "-r",
        help="Number of available raters (mutually exclusive with --rater-name).",
    ),
    per_rater: int = typer.Option(
        10,
        "--per-rater",
        "-p",
        min=1,
        help="Comparisons to allocate per rater (default: 10).",
    ),
    rater_names: Optional[List[str]] = typer.Option(
        None,
        "--rater-name",
        "-n",
        help="Explicit rater names (repeat option per rater or supply comma-separated values).",
    ),
    include_status: StatusSelector = typer.Option(
        StatusSelector.ALL,
        "--include-status",
        case_sensitive=False,
        help="Select from 'core' (84 comparisons) or 'all' (core + extras).",
    ),
) -> None:
    """Redistribute comparison pairs and export a new rater assignment file."""
    try:
        pairs_path = pairs_csv or Path(typer.prompt("Path to pairs CSV"))
        output_path = output_csv or Path(typer.prompt("Path for output CSV"))

        comparisons = read_pairs(pairs_path)

        if rater_names:
            names = build_rater_list(None, rater_names)
        else:
            if raters is None:
                raters = typer.prompt("How many raters will attend?", type=int)
            names = build_rater_list(raters, None)

        total_needed = len(names) * per_rater
        selected: List[Comparison] = select_comparisons(comparisons, include_status, total_needed)
        assignments = assign_pairs(selected, names, per_rater)
        write_assignments(output_path, assignments)
    except (FileNotFoundError, ValueError) as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    statuses = sorted({comparison.status for _, comparison in assignments})
    typer.secho(
        f"Generated assignments for {len(names)} raters "
        f"({per_rater} comparisons each).",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Pairs drawn from statuses: {', '.join(statuses)}")
    typer.echo(f"Output written to {output_path}")


if __name__ == "__main__":
    app()
