"""Thin wrapper exposing ENG5 LOWER5 mock parity tests.

The full implementations live in
``eng5_mock_parity_lower5_parity_impl.py`` and
``eng5_mock_parity_lower5_diagnostics_impl.py`` to keep this module small
and aligned with modular LoC guidelines.
"""

from __future__ import annotations

from tests.eng5_profiles.eng5_mock_parity_lower5_diagnostics_impl import (
    TestEng5MockParityLower5Diagnostics,
)
from tests.eng5_profiles.eng5_mock_parity_lower5_parity_impl import (
    TestEng5MockParityLower5Parity,
)


class TestEng5MockParityLower5(
    TestEng5MockParityLower5Parity,
    TestEng5MockParityLower5Diagnostics,
):
    """Combined ENG5 LOWER5 mock parity and diagnostics suite."""

    pass


__all__ = ["TestEng5MockParityLower5"]
