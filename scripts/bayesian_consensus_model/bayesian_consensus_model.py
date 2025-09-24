"""High-level interface for the kernel-smoothed ordinal consensus model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd

from .models.ordinal_kernel import GRADES, KernelConfig, OrdinalKernelModel


@dataclass
class ConsensusResult:
    essay_id: str
    consensus_grade: str
    confidence: float
    grade_probabilities: Dict[str, float]
    sample_size: int
    ability: float
    expected_grade_index: float


class ConsensusModel:
    """Wrapper around the ordinal kernel implementation."""

    def __init__(self, config: KernelConfig | None = None) -> None:
        self._model = OrdinalKernelModel(config)
        self._results: Dict[str, ConsensusResult] = {}

    @staticmethod
    def prepare_data(ratings: pd.DataFrame) -> pd.DataFrame:
        return OrdinalKernelModel.prepare_data(ratings)

    def fit(self, ratings: pd.DataFrame) -> None:
        self._model.fit(ratings)
        raw_results = self._model.consensus()
        self._results = {}
        for essay_id, result in raw_results.items():
            self._results[essay_id] = ConsensusResult(
                essay_id=essay_id,
                consensus_grade=result["consensus_grade"],
                confidence=result["confidence"],
                grade_probabilities=result["probabilities"],
                sample_size=result["sample_size"],
                ability=result["expected_grade_index"],
                expected_grade_index=result["expected_grade_index"],
            )

    def get_consensus(self) -> Dict[str, ConsensusResult]:
        if not self._results:
            raise ValueError("Model must be fitted before requesting consensus")
        return dict(self._results)

    @property
    def rater_metrics(self) -> pd.DataFrame:
        return self._model.rater_metrics

__all__ = [
    "ConsensusModel",
    "ConsensusResult",
    "KernelConfig",
    "GRADES",
]
