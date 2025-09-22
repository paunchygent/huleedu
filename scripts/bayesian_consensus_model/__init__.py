"""Bayesian consensus model for essay grading.

Exposes the improved Bayesian ordinal regression implementation, validation
helpers, and the production-ready consensus grading solution.
"""

from .bayesian_consensus_model import (
    ConsensusResult,
    ImprovedBayesianModel,
    ModelConfig,
)
from .model_validation import ModelValidator, ValidationResult, validate_model
from .consensus_grading_solution import (
    ConsensusResult as HybridConsensusResult,
    PrincipledConsensusGrader,
    ConsensusGradingConfig,
)

__all__ = [
    "ImprovedBayesianModel",
    "ModelConfig",
    "ConsensusResult",
    "ModelValidator",
    "ValidationResult",
    "validate_model",
    "PrincipledConsensusGrader",
    "ConsensusGradingConfig",
    "HybridConsensusResult",
]
