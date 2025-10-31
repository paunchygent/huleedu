from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

if __package__ in (None, ""):
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from .d_optimal_workflow import (  # type: ignore
        DEFAULT_ANCHOR_ORDER,
        DesignDiagnostics,
        OptimizationResult,
        optimize_schedule,
        run_synthetic_optimization,
        write_design,
    )
except ImportError:  # pragma: no cover - direct execution fallback
    from scripts.bayesian_consensus_model.d_optimal_workflow import (  # type: ignore[attr-defined]
        DEFAULT_ANCHOR_ORDER,
        DesignDiagnostics,
        OptimizationResult,
        optimize_schedule,
        run_synthetic_optimization,
        write_design,
    )

SESSION2_DIR = Path(__file__).resolve().parent / "session_2_planning" / "20251027-143747"
SESSION2_PAIRS = SESSION2_DIR / "session2_pairs.csv"
SESSION2_OUTPUT = SESSION2_DIR / "session2_pairs_optimized.csv"


def run_synthetic(args: argparse.Namespace) -> None:
    total_slots = args.total_slots or 36
    result = run_synthetic_optimization(
        total_slots=total_slots,
        max_repeat=args.max_repeat,
        seed=args.seed,
    )
    _print_results("D-Optimal Prototype (Synthetic)", result)


def run_session2(args: argparse.Namespace) -> None:
    result = optimize_schedule(
        SESSION2_PAIRS,
        total_slots=args.total_slots,
        max_repeat=args.max_repeat,
        anchor_order=DEFAULT_ANCHOR_ORDER,
        status_filter=("core",),
    )
    _print_results("D-Optimal Prototype (Session 2 Data)", result)

    output_path = args.output or SESSION2_OUTPUT
    write_design(result.optimized_design, output_path)
    print(f"\nOptimized schedule written to {output_path}")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="D-optimal pairing prototype.")
    parser.add_argument(
        "--mode",
        choices=("synthetic", "session2"),
        default="session2",
        help="Select synthetic demo or Session 2 data run (default: session2).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination CSV for optimized schedule when running in session2 mode.",
    )
    parser.add_argument(
        "--max-repeat",
        type=int,
        default=3,
        help="Maximum allowed repeat count for non-locked pairs (default: 3).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=17,
        help="Random seed for the synthetic baseline generator (default: 17).",
    )
    parser.add_argument(
        "--total-slots",
        type=int,
        help="Target number of comparisons (defaults to baseline count in session2 or 36 in synthetic mode).",
    )
    return parser.parse_args(argv)


def _print_results(title: str, result: OptimizationResult) -> None:
    print(f"=== {title} ===")
    print(f"Students:             {len(result.students)}")
    print(f"Baseline comparisons: {len(result.baseline_design)}")
    print(f"Optimized comparisons:{len(result.optimized_design)}")
    print(f"Baseline log-det:     {result.baseline_log_det:.4f}")
    print(f"Optimized log-det:    {result.optimized_log_det:.4f}")
    print(f"Gain:                 {result.log_det_gain:.4f}")

    _print_distribution("baseline", result.baseline_diagnostics)
    _print_distribution("optimized", result.optimized_diagnostics)


def _print_distribution(label: str, diagnostics: DesignDiagnostics) -> None:
    print(f"\nType distribution ({label}):")
    for key, value in diagnostics.type_counts.items():
        print(f"  {key:<16} {value}")


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    if args.mode == "synthetic":
        run_synthetic(args)
    else:
        run_session2(args)


if __name__ == "__main__":
    main()
