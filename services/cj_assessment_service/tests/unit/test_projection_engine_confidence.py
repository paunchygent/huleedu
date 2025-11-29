"""Unit tests for ProjectionEngine._entropy_to_confidence with SE-based caps.

Tests the confidence calculation that combines entropy-based confidence with
Bradley-Terry standard error (SE) to produce realistic confidence labels.

High SE (uncertain BT estimates) should cap confidence regardless of entropy.
"""

from __future__ import annotations

import math

import pytest

from services.cj_assessment_service.cj_core_logic.grade_projection.projection_engine import (
    ProjectionEngine,
)


class TestEntropyToConfidenceWithSE:
    """Tests for _entropy_to_confidence method incorporating BT standard error."""

    @pytest.fixture
    def engine(self) -> ProjectionEngine:
        """Create ProjectionEngine instance for direct method testing."""
        return ProjectionEngine()

    @pytest.mark.parametrize(
        "entropy, bt_se, expected_label",
        [
            # High SE (>=1.5) forces LOW regardless of entropy
            (0.1, 1.5, "LOW"),
            (0.2, 1.6, "LOW"),
            (0.3, 2.0, "LOW"),
            # Medium SE (1.0-1.5) caps at MID
            (0.1, 1.0, "MID"),
            (0.2, 1.2, "MID"),
            (0.3, 1.4, "MID"),
            # Low SE (<0.5) allows entropy-based HIGH
            (0.2, 0.3, "HIGH"),
            (0.3, 0.4, "HIGH"),
            # High entropy with low SE: geometric mean effect
            # entropy=0.8, se=0.3 -> conf=sqrt(0.2*1.0)≈0.45 -> MID
            (0.8, 0.3, "MID"),
            # entropy=0.9, se=0.2 -> conf=sqrt(0.1*1.0)≈0.32 -> LOW
            (0.9, 0.2, "LOW"),
        ],
    )
    def test_se_based_confidence_caps(
        self, engine: ProjectionEngine, entropy: float, bt_se: float, expected_label: str
    ) -> None:
        """SE-based caps override entropy-based confidence when appropriate."""
        _, label = engine._entropy_to_confidence(entropy, bt_se)
        assert label == expected_label

    @pytest.mark.parametrize(
        "entropy, expected_label, expected_score",
        [
            # Original entropy-only behavior when bt_se=None
            (0.3, "HIGH", 0.7),
            (0.6, "MID", 0.4),
            (0.8, "LOW", 0.2),
        ],
    )
    def test_none_se_fallback(
        self,
        engine: ProjectionEngine,
        entropy: float,
        expected_label: str,
        expected_score: float,
    ) -> None:
        """None SE falls back to entropy-only behavior."""
        score, label = engine._entropy_to_confidence(entropy, bt_se=None)
        assert label == expected_label
        assert score == pytest.approx(expected_score)

    @pytest.mark.parametrize(
        "entropy, bt_se",
        [
            (0.4, 0.3),  # entropy_conf=0.6, se_conf=1.0
            (0.2, 0.7),  # entropy_conf=0.8, se_conf=0.8
            (0.5, 1.2),  # entropy_conf=0.5, se_conf=0.6
        ],
    )
    def test_geometric_mean_score(
        self, engine: ProjectionEngine, entropy: float, bt_se: float
    ) -> None:
        """Confidence score is geometric mean of entropy and SE factors."""
        entropy_conf = 1.0 - entropy

        # Compute expected SE confidence factor
        if bt_se >= 1.5:
            se_conf = 0.3
        elif bt_se >= 1.0:
            se_conf = 0.6
        elif bt_se >= 0.5:
            se_conf = 0.8
        else:
            se_conf = 1.0

        expected_score = math.sqrt(entropy_conf * se_conf)

        score, _ = engine._entropy_to_confidence(entropy, bt_se)
        assert score == pytest.approx(expected_score, rel=0.01)

    def test_confidence_score_range(self, engine: ProjectionEngine) -> None:
        """Confidence scores are always in valid [0, 1] range."""
        test_cases = [
            (0.0, 0.1),
            (0.5, 0.5),
            (1.0, 2.0),
            (0.2, 1.5),
        ]
        for entropy, bt_se in test_cases:
            score, _ = engine._entropy_to_confidence(entropy, bt_se)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for ({entropy}, {bt_se})"

    def test_valid_labels_only(self, engine: ProjectionEngine) -> None:
        """Only valid confidence labels are returned."""
        valid_labels = {"HIGH", "MID", "LOW"}
        test_cases = [
            (0.1, 0.2),
            (0.5, 1.0),
            (0.9, 1.8),
            (0.3, None),
        ]
        for entropy, bt_se in test_cases:
            _, label = engine._entropy_to_confidence(entropy, bt_se)
            assert label in valid_labels, f"Invalid label {label} for ({entropy}, {bt_se})"
