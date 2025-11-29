"""Unit tests for Bradley-Terry standard error computation.

Tests the low-level `compute_bt_standard_errors` function from bt_inference.py,
covering reference selection (anchor vs student), SE capping, and edge cases.

Per rule 075: Single responsibility test file for SE computation behavior.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.cj_assessment_service.cj_core_logic import bt_inference


class TestBTSEComputation:
    """Tests for compute_bt_standard_errors function."""

    class TestReferenceSelection:
        """Reference (SE=0) selection behavior.

        The BT model requires a reference item with fixed SE=0 for identifiability.
        When anchors are provided, the last anchor should be used as reference.
        When no anchors provided, falls back to last item with a warning.
        """

        @pytest.fixture
        def sample_comparison_data(self) -> tuple[int, list[tuple[int, int]], np.ndarray]:
            """Create sample data for 10 items with connected comparisons."""
            n_items = 10
            # Create a chain of comparisons: 0>1, 1>2, ..., 8>9
            pairs = [(i, i + 1) for i in range(n_items - 1)]
            # Add some cross-links for better connectivity
            pairs.extend([(0, 5), (2, 7), (4, 9)])
            theta = np.linspace(-1.0, 1.0, n_items)  # Spread scores
            return n_items, pairs, theta

        @pytest.mark.parametrize(
            "anchor_indices, expected_ref_idx",
            [
                ([5, 10, 15], 15),  # Last anchor is reference (index 15)
                ([7], 7),  # Single anchor becomes reference
                ([0, 1, 2], 2),  # Last of multiple anchors
            ],
            ids=["multiple_anchors", "single_anchor", "first_anchors"],
        )
        def test_anchor_becomes_reference(
            self,
            anchor_indices: list[int],
            expected_ref_idx: int,
        ) -> None:
            """Reference item (SE=0) should be the last anchor when anchors provided."""
            # Use enough items to cover all anchor indices
            n_items = max(anchor_indices) + 1
            # Create minimal connected comparison graph
            pairs = [(i, i + 1) for i in range(n_items - 1)]
            theta = np.linspace(-1.0, 1.0, n_items)

            se = bt_inference.compute_bt_standard_errors(
                n_items=n_items,
                pairs=pairs,
                theta=theta,
                anchor_indices=anchor_indices,
            )

            assert se[expected_ref_idx] == 0.0, (
                f"Expected SE[{expected_ref_idx}] = 0 (reference), got {se[expected_ref_idx]}"
            )
            # All other items should have SE > 0
            for i in range(n_items):
                if i != expected_ref_idx:
                    assert se[i] > 0.0, f"Expected SE[{i}] > 0, got {se[i]}"

        @pytest.mark.parametrize(
            "anchor_indices",
            [None, []],
            ids=["none", "empty_list"],
        )
        def test_fallback_to_last_item_when_no_anchors(
            self,
            anchor_indices: list[int] | None,
            sample_comparison_data: tuple[int, list[tuple[int, int]], np.ndarray],
        ) -> None:
            """When no anchors provided, last item becomes reference.

            Note: Warning is logged via structlog but we test behavior, not logs
            per rule 075: "FORBIDDEN: Fragile log message testing".
            """
            n_items, pairs, theta = sample_comparison_data

            se = bt_inference.compute_bt_standard_errors(
                n_items=n_items,
                pairs=pairs,
                theta=theta,
                anchor_indices=anchor_indices,
            )

            # Last item should be reference (SE=0)
            assert se[n_items - 1] == 0.0
            # First item should have SE > 0 (not the reference)
            assert se[0] > 0.0

        def test_students_never_zero_se_when_anchors_provided(
            self,
            sample_comparison_data: tuple[int, list[tuple[int, int]], np.ndarray],
        ) -> None:
            """Student items should never have SE=0 when anchors are provided."""
            n_items, pairs, theta = sample_comparison_data
            # Mark indices 5, 7, 9 as anchors
            anchor_indices = [5, 7, 9]
            student_indices = [i for i in range(n_items) if i not in anchor_indices]

            se = bt_inference.compute_bt_standard_errors(
                n_items=n_items,
                pairs=pairs,
                theta=theta,
                anchor_indices=anchor_indices,
            )

            # All student items should have SE > 0
            for i in student_indices:
                assert se[i] > 0.0, f"Student item {i} has SE=0, should be > 0"

            # Only the reference anchor (last = 9) should have SE=0
            assert se[9] == 0.0

    class TestSECapping:
        """SE value capping behavior."""

        def test_extreme_se_capped_at_max(
            self,
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            """SE computation should respect the configured upper cap."""
            n_items = 3

            def fake_pinv(
                matrix: np.ndarray,  # noqa: ARG001
                rcond: float = 1e-10,  # noqa: ARG001
            ) -> np.ndarray:
                # Return a covariance matrix with very large diagonal entries to
                # force SE values that would exceed the configured cap.
                return np.array([[100.0, 0.0], [0.0, 100.0]])

            monkeypatch.setattr(bt_inference, "pinv", fake_pinv)

            theta = np.array([0.0, 0.1, -0.1])
            pairs = [(0, 1)]

            se = bt_inference.compute_bt_standard_errors(n_items, pairs, theta)

            assert se.shape == (n_items,)
            assert np.all(se >= 0.0)
            assert np.max(se) <= bt_inference.BT_STANDARD_ERROR_MAX
            # At least one item should have been capped
            assert np.any(np.isclose(se, bt_inference.BT_STANDARD_ERROR_MAX))

    class TestEdgeCases:
        """Edge cases and boundary conditions."""

        def test_single_item_returns_zero_array(self) -> None:
            """Single item should return zero SE (no meaningful comparison)."""
            se = bt_inference.compute_bt_standard_errors(
                n_items=1,
                pairs=[],
                theta=np.array([0.0]),
            )

            assert se.shape == (1,)
            assert se[0] == 0.0

        def test_no_pairs_returns_default_se(self) -> None:
            """No comparison pairs should return default SE values with warning."""
            n_items = 5
            theta = np.zeros(n_items)

            se = bt_inference.compute_bt_standard_errors(
                n_items=n_items,
                pairs=[],
                theta=theta,
            )

            assert se.shape == (n_items,)
            # Should return default SE of 0.5 when no pairs
            assert np.allclose(se, 0.5)

        def test_two_items_minimal_case(self) -> None:
            """Minimal two-item comparison should produce valid SE."""
            n_items = 2
            pairs = [(0, 1)]  # Item 0 beats item 1
            theta = np.array([0.5, -0.5])

            se = bt_inference.compute_bt_standard_errors(
                n_items=n_items,
                pairs=pairs,
                theta=theta,
            )

            assert se.shape == (n_items,)
            # Reference item (last) has SE=0
            assert se[1] == 0.0
            # Other item has positive SE
            assert se[0] > 0.0
