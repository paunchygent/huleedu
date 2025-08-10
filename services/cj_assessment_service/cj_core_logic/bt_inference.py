"""Bradley-Terry inference with analytical standard errors.

This module provides statistical inference for Bradley-Terry models,
including computation of standard errors via Fisher Information matrix.
"""

from __future__ import annotations

import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger
from numpy.linalg import pinv

logger = create_service_logger("cj_assessment.bt_inference")


def compute_bt_standard_errors(
    n_items: int,
    pairs: list[tuple[int, int]],  # (winner_idx, loser_idx)
    theta: np.ndarray,
) -> np.ndarray:
    """Compute analytical standard errors for Bradley-Terry abilities.

    Uses Fisher Information matrix (negative Hessian of log-likelihood).
    Employs a reference parameter for identifiability and Moore-Penrose
    pseudoinverse for numerical stability.

    Args:
        n_items: Number of items (essays) being compared
        pairs: List of comparison outcomes as (winner_idx, loser_idx) tuples
        theta: Bradley-Terry ability parameters from choix

    Returns:
        Array of standard errors for each item

    Note:
        The last item is used as reference (SE = 0) for identifiability.
        This matches choix's parameterization approach.
    """
    assert theta.shape == (n_items,), f"Theta shape {theta.shape} doesn't match n_items {n_items}"

    if n_items < 2:
        return np.zeros(n_items)

    if not pairs:
        logger.warning("No comparison pairs provided, returning default SEs")
        return np.ones(n_items) * 0.5  # Default uncertainty when no comparisons

    # Use last item as reference for identifiability
    ref = n_items - 1
    active = [i for i in range(n_items) if i != ref]

    # Initialize Fisher Information matrix (Hessian)
    H = np.zeros((n_items - 1, n_items - 1), dtype=float)

    # Build Fisher Information from pairwise comparisons
    for w, l in pairs:
        if w < 0 or w >= n_items or l < 0 or l >= n_items:
            logger.warning(f"Invalid pair indices: ({w}, {l}) for n_items={n_items}")
            continue

        tw, tl = theta[w], theta[l]

        # Bradley-Terry probability: P(w > l) = exp(tw) / (exp(tw) + exp(tl))
        # For numerical stability, use log-space computation
        diff = tw - tl
        if abs(diff) > 10:  # Prevent overflow
            p = 1.0 if diff > 0 else 0.0
        else:
            exp_diff = np.exp(diff)
            p = exp_diff / (1.0 + exp_diff)

        # Variance term for logistic model
        v = p * (1.0 - p)

        # Update Hessian matrix
        if w != ref:
            iw = active.index(w)
            H[iw, iw] += v
        if l != ref:
            il = active.index(l)
            H[il, il] += v
        if w != ref and l != ref:
            iw = active.index(w)
            il = active.index(l)
            H[iw, il] -= v
            H[il, iw] -= v

    # Check condition number for numerical stability
    if H.size > 0:
        cond = np.linalg.cond(H)
        if cond > 1e10:
            logger.warning(
                f"Ill-conditioned Fisher Information matrix: condition number={cond:.2e}. "
                "Standard errors may be unreliable."
            )

    # Compute covariance matrix using pseudoinverse (robust to near-singular matrices)
    try:
        cov_active = pinv(H, rcond=1e-10)
    except Exception as e:
        logger.error(f"Failed to compute pseudoinverse: {e}")
        # Fallback to identity-like covariance
        cov_active = np.eye(len(active)) * 0.25

    # Extract standard errors from diagonal of covariance matrix
    se = np.zeros(n_items, dtype=float)
    for idx, i in enumerate(active):
        # Ensure non-negative variance (numerical safety)
        variance = cov_active[idx, idx]
        se[i] = float(np.sqrt(max(variance, 0.0)))

    # Reference item has zero SE by construction
    se[ref] = 0.0

    # Validate and cap extreme values
    max_reasonable_se = 2.0  # Cap at 2.0 for stability
    for i in range(n_items):
        if se[i] > max_reasonable_se:
            logger.warning(f"Capping extreme SE for item {i}: {se[i]:.3f} -> {max_reasonable_se}")
            se[i] = max_reasonable_se

    return se


def estimate_required_comparisons(
    n_items: int,
    target_se: float = 0.1,
    connectivity: float = 2.0,
) -> int:
    """Estimate number of comparisons needed for target standard error.

    This is a heuristic based on information theory and empirical observations.

    Args:
        n_items: Number of items to compare
        target_se: Desired standard error level
        connectivity: Average connections per item (typically 2-4)

    Returns:
        Estimated total number of comparisons needed
    """
    # Information gain per comparison decreases with more items
    # Rule of thumb: need ~k*n*log(n) comparisons for SE ≈ 1/sqrt(k*n)
    k = (1.0 / target_se) ** 2 / n_items
    estimated = int(k * n_items * np.log(n_items) * connectivity)

    # Ensure minimum comparisons for connectivity
    min_comparisons = int(n_items * connectivity)

    return max(estimated, min_comparisons)
