"""Forward-looking convergence harness specs for CJ Assessment (PR-7).

These tests are intentionally marked xfail and serve purely as behavioural
specs for the planned convergence harness work (US-005.4 / PR-7). They do
not exercise real code paths yet and are expected to be rewritten once the
harness is implemented.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="PR-7 convergence harness not yet implemented", strict=False)
def test_convergence_harness_stops_on_stability_before_max_iterations() -> None:
    """Convergence harness should stop once stability is achieved.

    Expected PR-7 behaviour (high-level):
    - The harness runs iterations of comparison waves against synthetic nets
      using the same BT scoring routines as production.
    - Stability checks start only after
      MIN_COMPARISONS_FOR_STABILITY_CHECK successful comparisons.
    - If BT score deltas fall below SCORE_STABILITY_THRESHOLD before
      MAX_ITERATIONS is reached, the harness must stop scheduling additional
      iterations even when global comparison budget remains.
    - Once implemented, this test should be replaced with a concrete
      scenario that constructs a small synthetic net and verifies that the
      harness exits early on stability.
    """

    assert False, "PR-7 convergence harness not implemented"


@pytest.mark.xfail(reason="PR-7 convergence harness not yet implemented", strict=False)
def test_convergence_harness_stops_after_max_iterations_or_budget() -> None:
    """Convergence harness must respect iteration and budget caps.

    Expected PR-7 behaviour (high-level):
    - Given MAX_ITERATIONS and MAX_PAIRWISE_COMPARISONS, the harness should
      stop scheduling new iterations when either cap is reached, even if
      score stability has not yet been achieved.
    - The harness should surface which cap fired (iterations vs budget) so
      downstream diagnostics and product docs can distinguish "not stable"
      from "capped" runs.
    - Once implemented, this test should be rewritten to drive the harness
      with an intentionally difficult synthetic net and assert that it stops
      on the configured caps.
    """

    assert False, "PR-7 convergence harness not implemented"
