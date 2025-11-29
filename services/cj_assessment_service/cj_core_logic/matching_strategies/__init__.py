"""Pair matching strategies for comparative judgment waves.

This module provides DI-swappable implementations of PairMatchingStrategyProtocol.
"""

from services.cj_assessment_service.cj_core_logic.matching_strategies.optimal_graph_matching import (  # noqa: E501
    OptimalGraphMatchingStrategy,
)

__all__ = ["OptimalGraphMatchingStrategy"]
