"""Execute workflow business logic for redistribute TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.widgets import Input, Select

from scripts.bayesian_consensus_model.d_optimal_workflow import (
    OptimizationResult,
    load_dynamic_spec,
    load_previous_comparisons_from_csv,
    load_students_from_csv,
    optimize_from_dynamic_spec,
    write_design,
)
from scripts.bayesian_consensus_model.redistribute_core import (
    Comparison,
    assign_pairs,
    build_rater_list,
    compute_quota_distribution,
    read_pairs,
    select_comparisons,
    write_assignments,
)


@dataclass
class OptimizerInputs:
    """Input data for optimizer."""

    students_csv: str
    students_manual: str
    anchors: str
    optimizer_output: str
    previous_csv: str
    locked_pairs: str
    max_repeat: str
    include_anchor_anchor: str
    rater_names: str
    rater_count: str
    per_rater: str


@dataclass
class AssignmentInputs:
    """Input data for assignment generation."""

    output_path: str
    rater_names: str
    rater_count: str
    per_rater: str


@dataclass
class AssignmentResult:
    """Result of assignment generation."""

    quotas: dict[str, int]
    requested_total: int
    available_total: int
    output_path: Path


def extract_optimizer_inputs(
    query_one: callable,  # noqa: ANN001
) -> OptimizerInputs:
    """Extract optimizer inputs from TUI form.

    Args:
        query_one: Function to query TUI widgets by ID

    Returns:
        OptimizerInputs with all form values
    """
    return OptimizerInputs(
        students_csv=query_one("#students_csv_input", Input).value.strip(),
        students_manual=query_one("#students_input", Input).value.strip(),
        anchors=query_one("#anchors_input", Input).value.strip(),
        optimizer_output=query_one("#optimizer_output_input", Input).value.strip(),
        previous_csv=query_one("#previous_csv_input", Input).value.strip(),
        locked_pairs=query_one("#locked_pairs_input", Input).value.strip(),
        max_repeat=query_one("#optimizer_max_repeat_input", Input).value.strip(),
        include_anchor_anchor=query_one("#include_anchor_anchor_select", Select).value,
        rater_names=query_one("#rater_names_input", Input).value.strip(),
        rater_count=query_one("#rater_count_input", Input).value.strip(),
        per_rater=query_one("#per_rater_input", Input).value.strip(),
    )


def extract_assignment_inputs(
    query_one: callable,  # noqa: ANN001
) -> AssignmentInputs:
    """Extract assignment inputs from TUI form.

    Args:
        query_one: Function to query TUI widgets by ID

    Returns:
        AssignmentInputs with all form values
    """
    return AssignmentInputs(
        output_path=query_one("#output_input", Input).value.strip(),
        rater_names=query_one("#rater_names_input", Input).value.strip(),
        rater_count=query_one("#rater_count_input", Input).value.strip(),
        per_rater=query_one("#per_rater_input", Input).value.strip(),
    )


def run_optimizer(inputs: OptimizerInputs) -> tuple[OptimizationResult, Path, str]:
    """Run the D-optimal pair optimizer.

    Args:
        inputs: Optimizer input data from form

    Returns:
        Tuple of (optimization result, output path, students value for display)

    Raises:
        ValueError: If validation fails
        FileNotFoundError: If input files not found
    """
    # Get student IDs - try CSV first, fallback to manual entry
    if inputs.students_csv:
        csv_path = Path(inputs.students_csv)
        if not csv_path.exists():
            raise FileNotFoundError(f"Students CSV not found: {csv_path}")
        student_list = load_students_from_csv(csv_path)
        students_value = ", ".join(student_list)
    else:
        if not inputs.students_manual:
            raise ValueError("Provide students via CSV or comma-separated entry.")
        student_list = [s.strip() for s in inputs.students_manual.split(",") if s.strip()]
        if not student_list:
            raise ValueError("At least one student essay ID is required.")
        students_value = inputs.students_manual

    # Validate output path
    if not inputs.optimizer_output:
        raise ValueError("Optimization output path is required.")

    # Parse optional anchors
    anchor_list = None
    if inputs.anchors:
        anchor_list = [a.strip() for a in inputs.anchors.split(",") if a.strip()]

    # Parse locked pairs
    locked_pairs = None
    if inputs.locked_pairs:
        locked_list = []
        for pair_str in inputs.locked_pairs.split(";"):
            pair_str = pair_str.strip()
            if not pair_str:
                continue
            parts = [p.strip() for p in pair_str.split(",")]
            if len(parts) == 2:
                locked_list.append((parts[0], parts[1]))
            elif pair_str:
                raise ValueError(
                    f"Invalid locked pair format: '{pair_str}' (use 'essay_a,essay_b')"
                )
        locked_pairs = locked_list if locked_list else None

    # Calculate total slots from rater configuration
    per_rater_for_calc = int(inputs.per_rater) if inputs.per_rater else 10
    if per_rater_for_calc <= 0:
        raise ValueError("Comparisons per rater must be positive.")

    if inputs.rater_names:
        rater_names_for_calc = build_rater_list(None, [inputs.rater_names])
    else:
        if not inputs.rater_count:
            raise ValueError("Provide a rater count or explicit rater names.")
        rater_count_for_calc = int(inputs.rater_count)
        rater_names_for_calc = build_rater_list(rater_count_for_calc, None)

    total_slots = len(rater_names_for_calc) * per_rater_for_calc

    # Parse max repeat
    max_repeat = int(inputs.max_repeat) if inputs.max_repeat else 3
    if max_repeat <= 0:
        raise ValueError("Optimization max repeat must be positive.")

    # Parse include anchor-anchor toggle
    include_anchor_anchor = inputs.include_anchor_anchor == "yes"

    # Load previous comparisons if provided
    previous_comparisons = None
    if inputs.previous_csv:
        previous_csv_path = Path(inputs.previous_csv)
        previous_comparisons = load_previous_comparisons_from_csv(previous_csv_path)

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
    output_path = Path(inputs.optimizer_output)
    write_design(result.optimized_design, output_path)

    return result, output_path, students_value


def generate_assignments(
    inputs: AssignmentInputs,
    pairs_path: Path,
) -> AssignmentResult:
    """Generate rater assignments from optimized pairs.

    Args:
        inputs: Assignment input data from form
        pairs_path: Path to optimized pairs CSV

    Returns:
        AssignmentResult with quotas and output info

    Raises:
        ValueError: If validation fails
        FileNotFoundError: If pairs file not found
    """
    # Validate output path
    if not inputs.output_path:
        raise ValueError("Assignments CSV path is required.")
    output_path = Path(inputs.output_path)
    if output_path.is_dir():
        raise ValueError("Output path points to a directory; provide a file path.")

    # Load comparisons
    comparisons: list[Comparison] = read_pairs(pairs_path)

    # Parse rater configuration
    per_rater = int(inputs.per_rater) if inputs.per_rater else 10
    if per_rater <= 0:
        raise ValueError("Comparisons per rater must be positive.")

    if inputs.rater_names:
        names = build_rater_list(None, [inputs.rater_names])
    else:
        if not inputs.rater_count:
            raise ValueError("Provide a rater count or explicit rater names.")
        try:
            count = int(inputs.rater_count)
        except ValueError as exc:
            raise ValueError("Rater count must be an integer.") from exc
        names = build_rater_list(count, None)

    requested_total = len(names) * per_rater
    available_total = len(comparisons)

    if available_total == 0:
        raise ValueError("No comparisons available in pairs CSV.")

    # Generate assignments
    shortage = requested_total > available_total
    if shortage:
        quotas = compute_quota_distribution(names, per_rater, available_total)
        total_needed = sum(quotas.values())
        selected = select_comparisons(comparisons, total_needed)
        assignments = assign_pairs(selected, names, quotas)
    else:
        quotas = {name: per_rater for name in names}
        total_needed = requested_total
        selected = select_comparisons(comparisons, total_needed)
        assignments = assign_pairs(selected, names, per_rater)

    write_assignments(output_path, assignments)

    return AssignmentResult(
        quotas=quotas,
        requested_total=requested_total,
        available_total=available_total,
        output_path=output_path,
    )
