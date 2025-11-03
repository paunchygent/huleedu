from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..d_optimal_optimizer import DesignEntry

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
    new_design: List[DesignEntry]
    optimized_design: List[DesignEntry]
    baseline_log_det: float
    optimized_log_det: float
    baseline_diagnostics: DesignDiagnostics
    optimized_diagnostics: DesignDiagnostics
    anchor_adjacency_count: int
    required_pair_count: int
    locked_pair_count: int
    baseline_slots_in_design: int
    max_repeat: int

    @property
    def log_det_gain(self) -> float:
        return self.optimized_log_det - self.baseline_log_det

    @property
    def total_comparisons(self) -> int:
        return len(self.optimized_design)

    @property
    def new_comparisons(self) -> int:
        return len(self.new_design)

    @property
    def min_slots_required(self) -> int:
        return self.anchor_adjacency_count + self.locked_pair_count + self.required_pair_count


@dataclass(frozen=True)
class BaselinePayload:
    """Normalized payload describing dynamic baseline comparisons."""

    records: Sequence[Mapping[str, object]]
    anchor_order: Sequence[str]
    total_slots: Optional[int]


@dataclass(frozen=True)
class ComparisonRecord:
    """Historical comparison record feeding coverage analysis."""

    essay_a_id: str
    essay_b_id: str
    comparison_type: str  # student_anchor, student_student, anchor_anchor


@dataclass(frozen=True)
class DynamicSpec:
    """Dynamic input specification for optimizer without baseline files."""

    students: Sequence[str]
    anchors: Sequence[str]
    include_anchor_anchor: bool
    previous_comparisons: Sequence[ComparisonRecord]
    baseline_design: Sequence[DesignEntry]
    locked_pairs: Sequence[Tuple[str, str]]
    total_slots: int


__all__ = [
    "DEFAULT_ANCHOR_ORDER",
    "BaselinePayload",
    "ComparisonRecord",
    "DesignDiagnostics",
    "DynamicSpec",
    "OptimizationResult",
]
