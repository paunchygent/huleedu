"""Bayesian consensus model for essay grading.

This module provides an improved Bayesian ordinal regression model for
determining consensus grades from multiple raters.
"""

from .comparison_framework import (
    BaselineMethod,
    ComparisonFramework,
    ComparisonResult,
    SimpleMajority,
    TrimmedMean,
    WeightedMedian,
)
from .cross_validation import CrossValidator, CVResult
from .improved_bayesian_model import (
    ConsensusResult,
    ImprovedBayesianModel,
    ModelConfig,
)
from .model_validation import ModelValidator, ValidationResult, validate_model

__all__ = [
    "ImprovedBayesianModel",
    "ModelConfig",
    "ConsensusResult",
    "ModelValidator",
    "ValidationResult",
    "validate_model",
    "ComparisonFramework",
    "BaselineMethod",
    "SimpleMajority",
    "WeightedMedian",
    "TrimmedMean",
    "ComparisonResult",
    "CrossValidator",
    "CVResult",
]
