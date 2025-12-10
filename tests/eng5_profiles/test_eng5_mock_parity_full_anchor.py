"""Thin wrapper exposing ENG5 full-anchor mock parity tests.

The full implementation lives in
``eng5_mock_parity_full_anchor_parity_impl.py`` to keep this module
small and aligned with modular LoC guidelines.
"""

from __future__ import annotations

from tests.eng5_profiles.eng5_mock_parity_full_anchor_parity_impl import (
    TestEng5MockParityFullAnchorParity,
)


class TestEng5MockParityFullAnchor(TestEng5MockParityFullAnchorParity):
    """Combined ENG5 full-anchor mock parity suite."""

    pass


__all__ = ["TestEng5MockParityFullAnchor"]
