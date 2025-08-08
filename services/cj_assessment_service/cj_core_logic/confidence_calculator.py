"""Statistical confidence calculation for grade projections.

This module calculates confidence scores for grade projections based on
multiple factors including comparison count, score distribution, and
proximity to grade boundaries.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("cj_assessment.confidence")


class ConfidenceCalculator:
    """Calculates statistical confidence for grade projections.

    Uses multiple factors to determine confidence:
    - Number of comparisons for the essay
    - Score variance in the batch
    - Distance from grade boundaries
    - Presence of anchor essays
    """

    # Confidence thresholds
    HIGH_THRESHOLD = 0.75
    MID_THRESHOLD = 0.40

    def __init__(self) -> None:
        self.logger = logger

    def calculate_confidence(
        self,
        bt_score: float,
        comparison_count: int,
        score_distribution: list[float],
        grade_boundaries: dict[str, float],
        has_anchors: bool,
    ) -> tuple[float, str]:
        """Calculate confidence score and label.

        Args:
            bt_score: Bradley-Terry score for the essay
            comparison_count: Number of comparisons involving this essay
            score_distribution: All BT scores in the batch
            grade_boundaries: Grade boundary thresholds
            has_anchors: Whether anchor essays are present

        Returns:
            Tuple of (confidence_score, confidence_label)
        """
        # Factor 1: Comparison count confidence
        # More comparisons = higher confidence
        # Sigmoid curve: 50% confidence at 5 comparisons, 90% at 15
        comparison_confidence = 1.0 / (1.0 + math.exp(-(comparison_count - 5) / 3))

        # Factor 2: Score distribution confidence
        # Higher variance in scores = easier to distinguish = higher confidence
        if len(score_distribution) > 1:
            score_std = np.std(score_distribution)
            # Normalize standard deviation to [0, 1] range
            # Assume max useful std is 0.3 (on 0-1 scale)
            distribution_confidence = min(float(score_std) / 0.3, 1.0)
        else:
            distribution_confidence = 0.5

        # Factor 3: Distance from grade boundaries
        # Further from boundaries = higher confidence
        boundary_confidence = self._calculate_boundary_confidence(bt_score, grade_boundaries)

        # Factor 4: Anchor essay bonus
        anchor_bonus = 0.15 if has_anchors else 0.0

        # Weighted average of factors
        weights = {
            "comparisons": 0.35,
            "distribution": 0.20,
            "boundaries": 0.35,
            "anchors": 0.10,
        }

        base_confidence = (
            weights["comparisons"] * comparison_confidence
            + weights["distribution"] * distribution_confidence
            + weights["boundaries"] * boundary_confidence
            + weights["anchors"] * (1.0 if has_anchors else 0.0)
        )

        # Apply anchor bonus
        confidence_score = min(base_confidence + anchor_bonus, 1.0)

        # Map to label
        confidence_label = self._map_score_to_label(confidence_score)

        self.logger.debug(
            "Calculated confidence",
            extra={
                "bt_score": bt_score,
                "comparison_count": comparison_count,
                "has_anchors": has_anchors,
                "confidence_score": confidence_score,
                "confidence_label": confidence_label,
                "factors": {
                    "comparison": comparison_confidence,
                    "distribution": distribution_confidence,
                    "boundary": boundary_confidence,
                },
            },
        )

        return confidence_score, confidence_label

    def _calculate_boundary_confidence(
        self,
        bt_score: float,
        grade_boundaries: dict[str, float],
    ) -> float:
        """Calculate confidence based on distance from grade boundaries.

        Args:
            bt_score: The Bradley-Terry score
            grade_boundaries: Dict of grade -> minimum BT score

        Returns:
            Confidence score based on boundary distance
        """
        # Get all boundary values
        boundaries = sorted(grade_boundaries.values())

        if not boundaries:
            return 0.5

        # Find the closest boundary
        min_distance = 1.0
        for boundary in boundaries:
            distance = abs(bt_score - boundary)
            min_distance = min(min_distance, distance)

        # Convert distance to confidence
        # Max confidence at distance >= 0.15
        # Min confidence at distance = 0
        if min_distance >= 0.15:
            return 1.0
        else:
            return min_distance / 0.15

    def _map_score_to_label(self, score: float) -> str:
        """Map confidence score to label.

        Args:
            score: Confidence score (0.0-1.0)

        Returns:
            Confidence label: HIGH, MID, or LOW
        """
        if score >= self.HIGH_THRESHOLD:
            return "HIGH"
        elif score >= self.MID_THRESHOLD:
            return "MID"
        else:
            return "LOW"

    def calculate_batch_confidence_stats(
        self,
        confidence_scores: dict[str, float],
    ) -> dict[str, Any]:
        """Calculate aggregate confidence statistics for a batch.

        Args:
            confidence_scores: Dict of essay_id -> confidence_score

        Returns:
            Statistics dictionary with mean, std, distribution
        """
        if not confidence_scores:
            return {
                "mean": 0.0,
                "std": 0.0,
                "high_count": 0,
                "mid_count": 0,
                "low_count": 0,
            }

        scores = list(confidence_scores.values())
        labels = [self._map_score_to_label(s) for s in scores]

        return {
            "mean": float(np.mean(scores)),
            "std": float(np.std(scores)),
            "high_count": labels.count("HIGH"),
            "mid_count": labels.count("MID"),
            "low_count": labels.count("LOW"),
        }
