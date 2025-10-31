"""Evaluation harness for modular consensus model improvements."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Dict

import pandas as pd

from ..bayesian_consensus_model import ConsensusModel, ConsensusResult, KernelConfig

_FEATURE_FLAGS = (
    "use_argmax_decision",
    "use_loo_alignment",
    "use_precision_weights",
    "use_neutral_gating",
)


class ImprovementHarness:
    """Run comparative studies for consensus model improvements."""

    def __init__(self, ratings: pd.DataFrame, metadata: Dict[str, str] | None = None) -> None:
        required = {"essay_id", "rater_id", "grade"}
        missing = required - set(ratings.columns)
        if missing:
            raise ValueError(f"Ratings DataFrame missing columns: {sorted(missing)}")
        self._ratings = ratings[list(required)].copy()
        self._metadata = metadata or {}

    def _run_with_config(self, config: KernelConfig) -> Dict[str, ConsensusResult]:
        model = ConsensusModel(config)
        model.fit(self._ratings)
        return model.get_consensus()

    @staticmethod
    def _results_dataframe(results: Dict[str, ConsensusResult]) -> pd.DataFrame:
        rows = []
        for essay_id, result in results.items():
            rows.append(
                {
                    "essay_id": essay_id,
                    "consensus_grade": result.consensus_grade,
                    "confidence": result.confidence,
                    "expected_grade_index": result.expected_grade_index,
                    "neutral_ess": result.neutral_ess,
                    "needs_more_ratings": result.needs_more_ratings,
                }
            )
        return pd.DataFrame(rows).sort_values("essay_id").reset_index(drop=True)

    @staticmethod
    def _diff_metrics(base: pd.DataFrame, variant: pd.DataFrame) -> Dict[str, float | int]:
        merged = base.merge(variant, on="essay_id", suffixes=("_base", "_variant"))
        grade_changes = (merged["consensus_grade_base"] != merged["consensus_grade_variant"]).sum()
        delta_expected = merged["expected_grade_index_variant"] - merged["expected_grade_index_base"]
        delta_confidence = merged["confidence_variant"] - merged["confidence_base"]
        needs_more = merged["needs_more_ratings_variant"].sum()
        return {
            "grade_changes": int(grade_changes),
            "mean_delta_expected": float(delta_expected.mean()),
            "mean_abs_delta_expected": float(delta_expected.abs().mean()),
            "mean_delta_confidence": float(delta_confidence.mean()),
            "neutral_ess_mean": float(merged["neutral_ess_variant"].mean()),
            "needs_more_ratings_count": int(needs_more),
        }

    def compare_configurations(
        self,
        base_config: KernelConfig,
        variant_config: KernelConfig,
    ) -> Dict[str, object]:
        base_results = self._run_with_config(base_config)
        variant_results = self._run_with_config(variant_config)
        base_df = self._results_dataframe(base_results)
        variant_df = self._results_dataframe(variant_results)
        metrics = self._diff_metrics(base_df, variant_df)
        return {
            "base_config": asdict(base_config),
            "variant_config": asdict(variant_config),
            "metrics": metrics,
            "base_results": base_df,
            "variant_results": variant_df,
        }

    def run_ablation_study(self, base_config: KernelConfig | None = None) -> pd.DataFrame:
        base_config = base_config or KernelConfig()
        rows = []
        for flag in _FEATURE_FLAGS:
            target_config = replace(base_config, **{flag: True})
            comparison = self.compare_configurations(base_config, target_config)
            entry = {"flag": flag} | comparison["metrics"]
            rows.append(entry)
        return pd.DataFrame(rows)

    def generate_metrics(self, config: KernelConfig | None = None) -> Dict[str, float | int]:
        config = config or KernelConfig()
        results = self._results_dataframe(self._run_with_config(config))
        return {
            "mean_confidence": float(results["confidence"].mean()),
            "mean_expected_grade_index": float(results["expected_grade_index"].mean()),
            "neutral_ess_mean": float(results["neutral_ess"].mean()),
            "needs_more_ratings_count": int(results["needs_more_ratings"].sum()),
        }

    def create_report(self, base_config: KernelConfig | None = None) -> Dict[str, object]:
        base_config = base_config or KernelConfig()
        base_metrics = self.generate_metrics(base_config)
        ablation = self.run_ablation_study(base_config)
        full_config = replace(
            base_config,
            use_argmax_decision=True,
            use_loo_alignment=True,
            use_precision_weights=True,
            use_neutral_gating=True,
        )
        comparison = self.compare_configurations(base_config, full_config)
        return {
            "base_metrics": base_metrics,
            "ablation": ablation,
            "full_comparison": comparison,
        }
