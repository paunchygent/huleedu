"""Public interface for the Bayesian consensus modelling package."""

from .bayesian_consensus_model import (
    ConsensusModel,
    ConsensusResult,
    GRADES,
    KernelConfig,
)

__all__ = [
    "ConsensusModel",
    "ConsensusResult",
    "KernelConfig",
    "GRADES",
]
