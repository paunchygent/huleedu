"""Bradley-Terry inference with analytical standard errors.

This module provides statistical inference for Bradley-Terry models,
including computation of standard errors via Fisher Information matrix.
"""

from __future__ import annotations

import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger
from numpy.linalg import pinv

logger = create_service_logger("cj_assessment.bt_inference")

# Standard error values can become numerically unstable in degenerate graphs
# (for example, sparse or nearly disconnected comparison networks). To keep
# downstream diagnostics interpretable without affecting decision logic, we
# cap reported SEs at a conservative upper bound.
BT_STANDARD_ERROR_MAX: float = 2.0


def compute_bt_standard_errors(
    n_items: int,
    pairs: list[tuple[int, int]],  # (winner_idx, loser_idx)
    theta: np.ndarray,
    anchor_indices: list[int] | None = None,
) -> np.ndarray:
    """Compute analytical standard errors for Bradley-Terry abilities.

    Uses the Fisher Information matrix (negative Hessian of the log-likelihood)
    with a reference parameter for identifiability and Moore-Penrose
    pseudoinverse for numerical stability.

    Args:
        n_items: Number of items (essays) being compared.
        pairs: List of comparison outcomes as (winner_idx, loser_idx) tuples.
        theta: Bradley-Terry ability parameters from ``choix`` (shape: (n_items,)).
        anchor_indices: Optional list of indices that are anchor essays. If provided,
            the last anchor will be used as reference instead of the last item.

    Returns:
        Array of standard errors for each item (length ``n_items``).

    Notes:
        * An anchor item is preferred as reference (SE = 0) for identifiability.
        * Falls back to last item if no anchors provided.
        * Reported SE values are capped at ``BT_STANDARD_ERROR_MAX`` purely for
          numerical safety and observability. This cap does **not** feed into
          any completion, stability, or success-rate gating logic.
    """
    assert theta.shape == (n_items,), f"Theta shape {theta.shape} doesn't match n_items {n_items}"

    if n_items < 2:
        return np.zeros(n_items)

    if not pairs:
        logger.warning("No comparison pairs provided, returning default SEs")
        return np.ones(n_items) * 0.5  # Default uncertainty when no comparisons

    # Select reference: prefer anchors over student essays
    if anchor_indices:
        ref = anchor_indices[-1]  # Use last anchor as reference
    else:
        ref = n_items - 1
        logger.warning(
            "No anchor indices provided for BT SE computation, using last item as reference"
        )
    active = [i for i in range(n_items) if i != ref]

    # Initialize Fisher Information matrix (Hessian)
    H = np.zeros((n_items - 1, n_items - 1), dtype=float)

    # Build Fisher Information from pairwise comparisons
    for winner, loser in pairs:
        if winner < 0 or winner >= n_items or loser < 0 or loser >= n_items:
            logger.warning(f"Invalid pair indices: ({winner}, {loser}) for n_items={n_items}")
            continue

        tw, tl = theta[winner], theta[loser]

        # Bradley-Terry probability: P(w > l) = exp(tw) / (exp(tw) + exp(tl))
        # For numerical stability, use log-space computation.
        diff = tw - tl
        if abs(diff) > 10:  # Prevent overflow
            p = 1.0 if diff > 0 else 0.0
        else:
            exp_diff = np.exp(diff)
            p = exp_diff / (1.0 + exp_diff)

        # Variance term for logistic model
        v = p * (1.0 - p)

        # Update Hessian matrix
        if winner != ref:
            iw = active.index(winner)
            H[iw, iw] += v
        if loser != ref:
            il = active.index(loser)
            H[il, il] += v
        if winner != ref and loser != ref:
            iw = active.index(winner)
            il = active.index(loser)
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
    except Exception as e:  # pragma: no cover - defensive fallback
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
    for i in range(n_items):
        if se[i] > BT_STANDARD_ERROR_MAX:
            logger.warning(
                f"Capping extreme SE for item {i}: {se[i]:.3f} -> {BT_STANDARD_ERROR_MAX}",
            )
            se[i] = BT_STANDARD_ERROR_MAX

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
