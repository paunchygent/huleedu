from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

if __package__ in (None, ""):
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from .d_optimal_optimizer import (  # type: ignore[attr-defined]
        DesignEntry,
        PairCandidate,
        compute_log_det,
        derive_anchor_adjacency_constraints,
        select_design,
    )
    from .redistribute_core import load_comparisons_from_records  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - direct execution fallback
    from scripts.bayesian_consensus_model.d_optimal_optimizer import (  # type: ignore[attr-defined]
        DesignEntry,
        PairCandidate,
        compute_log_det,
        derive_anchor_adjacency_constraints,
        select_design,
    )
    from scripts.bayesian_consensus_model.redistribute_core import (  # type: ignore[attr-defined]
        load_comparisons_from_records,
    )

DEFAULT_ANCHOR_ORDER: List[str] = [
    "F+1",
    "F+2",
    "E-",
    "E+",
    "D-",
    "D+",
    "C-",
    "C+",
    "B1",
    "B2",
    "A1",
    "A2",
]


@dataclass(frozen=True)
class DesignDiagnostics:
    """Summary statistics describing a comparison schedule."""

    total_pairs: int
    type_counts: Dict[str, int]
    student_anchor_coverage: Dict[str, List[str]]
    repeat_counts: Dict[str, int]


@dataclass(frozen=True)
class OptimizationResult:
    """Container for optimizer output and related metrics."""

    students: Sequence[str]
    anchor_order: Sequence[str]
    baseline_design: List[DesignEntry]
    optimized_design: List[DesignEntry]
    baseline_log_det: float
    optimized_log_det: float
    baseline_diagnostics: DesignDiagnostics
    optimized_diagnostics: DesignDiagnostics
    anchor_adjacency_count: int
    required_pair_count: int
    max_repeat: int

    @property
    def log_det_gain(self) -> float:
        return self.optimized_log_det - self.baseline_log_det

    @property
    def total_comparisons(self) -> int:
        return len(self.optimized_design)

    @property
    def min_slots_required(self) -> int:
        return self.anchor_adjacency_count + self.required_pair_count


@dataclass(frozen=True)
class BaselinePayload:
    """Normalized payload describing dynamic baseline comparisons."""

    records: Sequence[Mapping[str, object]]
    anchor_order: Sequence[str]
    status_filter: Optional[Sequence[str]]
    total_slots: Optional[int]


def _unique_pair_count(pairs: Iterable[PairCandidate]) -> int:
    """Count distinct comparison pairs by essay IDs."""
    return len({pair.key() for pair in pairs})


def load_baseline_payload(
    path: Path,
    *,
    fallback_anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> BaselinePayload:
    """Parse a JSON payload describing baseline comparisons for optimization."""

    if not path.exists():
        raise FileNotFoundError(f"Baseline JSON not found: {path}")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON payload in {path}") from exc

    anchor_order: Sequence[str] = list(fallback_anchor_order)
    status_filter: Optional[Sequence[str]] = None
    total_slots: Optional[int] = None

    def _normalize_string_sequence(value: object, field: str) -> List[str]:
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise ValueError(f"'{field}' must be an array of strings.")
        return [str(item) for item in value]

    if isinstance(raw, Mapping):
        records_obj = (
            raw["comparisons"]
            if "comparisons" in raw
            else raw.get("records")
        )
        if records_obj is None:
            raise ValueError("Baseline payload must include a 'comparisons' array.")
        if "anchor_order" in raw:
            anchor_order = _normalize_string_sequence(raw["anchor_order"], "anchor_order")
        if "status_filter" in raw:
            status_filter = _normalize_string_sequence(raw["status_filter"], "status_filter")
        if "total_slots" in raw and raw["total_slots"] is not None:
            try:
                total_slots = int(raw["total_slots"])
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError("'total_slots' must be an integer if supplied.") from exc
    elif isinstance(raw, Sequence):
        records_obj = raw
    else:
        raise ValueError("Baseline payload must be a JSON object or array.")

    if not isinstance(records_obj, Sequence):
        raise ValueError("'comparisons' must be an array of objects.")

    normalized_records: List[Mapping[str, object]] = []
    for index, record in enumerate(records_obj):
        if not isinstance(record, Mapping):
            raise ValueError(f"Comparison at index {index} is not an object.")
        normalized_records.append(dict(record))

    if not anchor_order:
        raise ValueError("Anchor order cannot be empty.")

    return BaselinePayload(
        records=normalized_records,
        anchor_order=list(anchor_order),
        status_filter=list(status_filter) if status_filter is not None else None,
        total_slots=total_slots,
    )


def optimize_from_payload(
    payload: BaselinePayload,
    *,
    total_slots: int | None,
    max_repeat: int,
    anchor_order: Sequence[str] | None = None,
    status_filter: Iterable[str] | None = ("core",),
) -> OptimizationResult:
    """Run optimization for a pre-normalized baseline payload."""

    effective_slots = total_slots if total_slots is not None else payload.total_slots
    effective_anchor_order = (
        list(anchor_order) if anchor_order is not None else list(payload.anchor_order)
    )
    payload_status = payload.status_filter
    effective_status_filter: Iterable[str] | None
    if status_filter is not None:
        effective_status_filter = status_filter
    else:
        effective_status_filter = payload_status

    return optimize_schedule(
        pairs_path=None,
        total_slots=effective_slots,
        max_repeat=max_repeat,
        anchor_order=effective_anchor_order,
        status_filter=effective_status_filter,
        baseline_records=payload.records,
    )


def load_baseline_design(
    pairs_path: Path,
    *,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
    status_filter: Iterable[str] | None = ("core",),
) -> Tuple[List[str], List[DesignEntry]]:
    """Load a baseline design from CSV for optimization."""
    if not pairs_path.exists():
        raise FileNotFoundError(f"Pairs CSV not found: {pairs_path}")

    anchors = set(anchor_order)
    students: set[str] = set()
    design: List[DesignEntry] = []
    statuses = {status.lower() for status in status_filter} if status_filter is not None else None

    with pairs_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"essay_a_id", "essay_b_id", "comparison_type", "status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            field_list = ", ".join(sorted(missing))
            raise ValueError(f"Pairs CSV missing required columns: {field_list}")

        for row in reader:
            status_value = (row.get("status") or "").lower()
            if statuses is not None and status_value not in statuses:
                continue
            candidate = PairCandidate(
                essay_a=row["essay_a_id"],
                essay_b=row["essay_b_id"],
                comparison_type=row["comparison_type"],
            )
            design.append(DesignEntry(candidate))
            for essay in (candidate.essay_a, candidate.essay_b):
                if essay not in anchors:
                    students.add(essay)

    if not design:
        raise ValueError("No comparisons matched the requested status filter.")

    return sorted(students), design


def load_baseline_from_records(
    records: Iterable[Mapping[str, object]],
    *,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
    status_filter: Optional[Iterable[str]] = ("core",),
) -> Tuple[List[str], List[DesignEntry]]:
    """Load a baseline design from in-memory records."""
    raw_comparisons = load_comparisons_from_records(records)
    statuses = {status.lower() for status in status_filter} if status_filter is not None else None
    anchors = set(anchor_order)
    students: set[str] = set()
    design: List[DesignEntry] = []

    for comparison in raw_comparisons:
        if statuses is not None and comparison.status.lower() not in statuses:
            continue
        candidate = PairCandidate(
            essay_a=comparison.essay_a_id,
            essay_b=comparison.essay_b_id,
            comparison_type=comparison.comparison_type,
        )
        design.append(DesignEntry(candidate))
        for essay in (candidate.essay_a, candidate.essay_b):
            if essay not in anchors:
                students.add(essay)

    if not design:
        raise ValueError("No comparisons matched the requested status filter.")

    return sorted(students), design


def derive_student_anchor_requirements(
    baseline_design: Sequence[DesignEntry],
    anchor_order: Sequence[str],
) -> List[PairCandidate]:
    """Derive minimum student-anchor comparisons needed to preserve brackets."""
    anchor_index = {anchor: idx for idx, anchor in enumerate(anchor_order)}
    student_to_anchors: Dict[str, set[str]] = defaultdict(set)

    for entry in baseline_design:
        if entry.candidate.comparison_type != "student_anchor":
            continue
        essay_a = entry.candidate.essay_a
        essay_b = entry.candidate.essay_b
        if essay_a in anchor_index and essay_b in anchor_index:
            continue
        if essay_a in anchor_index:
            anchor = essay_a
            student = essay_b
        elif essay_b in anchor_index:
            anchor = essay_b
            student = essay_a
        else:
            continue
        student_to_anchors[student].add(anchor)

    requirements: List[PairCandidate] = []
    seen: set[Tuple[str, str]] = set()
    for student, anchors in student_to_anchors.items():
        if not anchors:
            continue
        ordered = sorted(anchors, key=lambda name: anchor_index[name])
        if len(ordered) >= 3:
            picks = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        else:
            picks = ordered
        for anchor in picks:
            key = (student, anchor)
            if key in seen:
                continue
            requirements.append(PairCandidate(student, anchor, "student_anchor"))
            seen.add(key)
    return requirements


def summarize_design(
    design: Sequence[DesignEntry],
    anchor_order: Sequence[str],
) -> DesignDiagnostics:
    """Return design diagnostics."""
    anchor_index = {anchor: idx for idx, anchor in enumerate(anchor_order)}
    anchor_set = set(anchor_order)

    type_counts: Counter[str] = Counter()
    coverage: Dict[str, set[str]] = defaultdict(set)
    repeats: Counter[Tuple[str, str]] = Counter()

    for entry in design:
        candidate = entry.candidate
        type_counts[candidate.comparison_type] += 1
        repeats[candidate.key()] += 1

        if candidate.comparison_type != "student_anchor":
            continue
        a_is_anchor = candidate.essay_a in anchor_set
        b_is_anchor = candidate.essay_b in anchor_set
        if a_is_anchor == b_is_anchor:
            continue
        student = candidate.essay_b if a_is_anchor else candidate.essay_a
        anchor = candidate.essay_a if a_is_anchor else candidate.essay_b
        coverage[student].add(anchor)

    ordered_coverage: Dict[str, List[str]] = {}
    for student, anchors in coverage.items():
        sorted_anchors = sorted(
            list(anchors),
            key=lambda name: anchor_index.get(name, len(anchor_index)),
        )
        ordered_coverage[student] = sorted_anchors
    repeat_counts = {
        f"{pair[0]}|{pair[1]}": count
        for pair, count in repeats.items()
        if count > 1
    }

    return DesignDiagnostics(
        total_pairs=len(design),
        type_counts=dict(sorted(type_counts.items())),
        student_anchor_coverage={
            student: ordered_coverage[student] for student in sorted(ordered_coverage)
        },
        repeat_counts=repeat_counts,
    )


def write_design(design: Sequence[DesignEntry], output_path: Path, *, status: str = "core") -> None:
    """Persist a design to CSV using the standard comparison schema."""
    fieldnames = ["pair_id", "essay_a_id", "essay_b_id", "comparison_type", "status"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, entry in enumerate(design, start=1):
            writer.writerow(
                {
                    "pair_id": idx,
                    "essay_a_id": entry.candidate.essay_a,
                    "essay_b_id": entry.candidate.essay_b,
                    "comparison_type": entry.candidate.comparison_type,
                    "status": status,
                }
            )


def optimize_schedule(
    pairs_path: Optional[Path] = None,
    *,
    total_slots: int | None,
    max_repeat: int,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
    status_filter: Iterable[str] | None = ("core",),
    baseline_records: Optional[Iterable[Mapping[str, object]]] = None,
) -> OptimizationResult:
    """Run the optimizer against a baseline design and return metrics."""
    if baseline_records is not None:
        students, baseline_design = load_baseline_from_records(
            baseline_records,
            anchor_order=anchor_order,
            status_filter=status_filter,
        )
    else:
        if pairs_path is None:
            raise ValueError("Provide either pairs_path or baseline_records to optimize.")
        students, baseline_design = load_baseline_design(
            pairs_path,
            anchor_order=anchor_order,
            status_filter=status_filter,
        )
    if not students:
        raise ValueError("No student essays detected in the baseline design.")

    slots = total_slots if total_slots is not None else len(baseline_design)
    adjacency_pairs = derive_anchor_adjacency_constraints(anchor_order)
    required_pairs = derive_student_anchor_requirements(baseline_design, anchor_order)
    anchor_adjacency_count = _unique_pair_count(adjacency_pairs)
    required_pair_count = _unique_pair_count(required_pairs)
    min_slots_required = anchor_adjacency_count + required_pair_count
    if slots < min_slots_required:
        raise ValueError(
            "Minimum required slots not met: requested "
            f"{slots}, but anchor adjacency requires {anchor_adjacency_count} "
            f"and baseline coverage requires {required_pair_count} "
            f"(total {min_slots_required}). Increase total slots or relax the baseline payload."
        )

    optimized_design, _ = select_design(
        students,
        anchor_order,
        total_slots=slots,
        anchor_order=anchor_order,
        required_pairs=required_pairs,
        max_repeat=max_repeat,
    )

    combined_items = list(students) + list(anchor_order)
    index_map = {item: idx for idx, item in enumerate(combined_items)}
    baseline_log_det = compute_log_det(baseline_design, index_map)
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchor_order)
    optimized_diag = summarize_design(optimized_design, anchor_order)

    return OptimizationResult(
        students=students,
        anchor_order=list(anchor_order),
        baseline_design=baseline_design,
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_count,
        required_pair_count=required_pair_count,
        max_repeat=max_repeat,
    )


def _build_random_design(
    students: Sequence[str],
    anchors: Sequence[str],
    *,
    total_slots: int,
    max_repeat: int,
    seed: int,
) -> List[DesignEntry]:
    """Create a random baseline schedule for synthetic demonstrations."""
    import random

    candidates: List[PairCandidate] = []
    counts: Dict[Tuple[str, str], int] = {}
    design: List[DesignEntry] = []

    for student in students:
        for anchor in anchors:
            candidates.append(PairCandidate(student, anchor, "student_anchor"))
    for idx in range(len(students)):
        for jdx in range(idx + 1, len(students)):
            candidates.append(PairCandidate(students[idx], students[jdx], "student_student"))
    for idx in range(len(anchors)):
        for jdx in range(idx + 1, len(anchors)):
            candidates.append(PairCandidate(anchors[idx], anchors[jdx], "anchor_anchor"))

    rng = random.Random(seed)
    for _ in range(total_slots):
        eligible = [
            candidate
            for candidate in candidates
            if counts.get(candidate.key(), 0) < max_repeat
        ]
        if not eligible:
            break
        picked = rng.choice(eligible)
        design.append(DesignEntry(picked))
        counts[picked.key()] = counts.get(picked.key(), 0) + 1
    return design


def run_synthetic_optimization(
    *,
    total_slots: int,
    max_repeat: int,
    seed: int,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> OptimizationResult:
    """Execute the optimizer against a deterministic synthetic dataset."""
    students = ["JA24", "II24", "ES24", "EK24", "ER24", "TK24", "SN24", "HJ17"]

    baseline_design = _build_random_design(
        students,
        anchor_order,
        total_slots=total_slots,
        max_repeat=max_repeat,
        seed=seed,
    )

    adjacency_pairs = derive_anchor_adjacency_constraints(anchor_order)
    anchor_adjacency_count = _unique_pair_count(adjacency_pairs)
    required_pair_count = 0
    if total_slots < anchor_adjacency_count:
        raise ValueError(
            "Minimum required slots not met: requested "
            f"{total_slots}, but anchor adjacency requires {anchor_adjacency_count}. "
            "Increase total slots to run the synthetic demonstration."
        )

    optimized_design, _ = select_design(
        students,
        anchor_order,
        total_slots=total_slots,
        anchor_order=anchor_order,
        max_repeat=max_repeat,
    )

    index_map = {item: idx for idx, item in enumerate(list(students) + list(anchor_order))}
    baseline_log_det = compute_log_det(baseline_design, index_map)
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchor_order)
    optimized_diag = summarize_design(optimized_design, anchor_order)

    return OptimizationResult(
        students=list(students),
        anchor_order=list(anchor_order),
        baseline_design=baseline_design,
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_count,
        required_pair_count=required_pair_count,
        max_repeat=max_repeat,
    )
