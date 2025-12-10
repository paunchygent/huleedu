"""Thin wrapper exposing CJ generic mock parity tests.

The full implementations live in
``cj_mock_parity_generic_parity_impl.py`` and
``cj_mock_parity_generic_coverage_impl.py`` to keep this module small and
aligned with modular LoC guidelines.
"""

from __future__ import annotations

from tests.eng5_profiles.cj_mock_parity_generic_coverage_impl import (
    TestCJMockParityGenericCoverage,
)
from tests.eng5_profiles.cj_mock_parity_generic_parity_impl import (
    TestCJMockParityGenericParity,
)


class TestCJMockParityGeneric(TestCJMockParityGenericParity, TestCJMockParityGenericCoverage):
    """Combined CJ generic mock parity and coverage suite."""

    pass


__all__ = ["TestCJMockParityGeneric"]
