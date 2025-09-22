# Bayesian Consensus Grading

This package contains HuleEdu's Bayesian consensus grading toolkit. It provides a
probabilistic model for essay scoring, a principled production grader that
selects the right method based on data density, and a validation suite that
quantifies convergence, stability, and confidence.

## Components

- `ImprovedBayesianModel` (in `bayesian_consensus_model.py`)
  - PyMC-based ordered-logit model with reference-rater identification
  - Adaptive sampling and fixed-threshold simple mode for sparse matrices
  - Hybrid majority override when data are too thin to trust posterior mode
- `PrincipledConsensusGrader` (in `consensus_grading_solution.py`)
  - Chooses between full Bayesian inference and Wilson-score majority voting
  - Surfaces confidence intervals, method provenance, and scarcity warnings
- `ModelValidator` (in `model_validation.py`)
  - Runs JA24 regression checks, majority alignment, bootstrap stability, and
    posterior confidence interval diagnostics

`__init__.py` re-exports these symbols so downstream services can simply import
`ImprovedBayesianModel`, `PrincipledConsensusGrader`, and `ModelValidator`.

## Data Requirements & Hybrid Override

The Bayesian estimator needs enough signal to identify essay ability, rater
severity, and threshold location parameters. We enforce:

- **Minimum observations**: 50 essay–rater pairs before attempting the full
  MCMC model
- **Majority override**: for any essay with fewer than 50 ratings, if the top
  grade holds **≥ 60 %** of votes we return that grade directly. The result still
  carries the posterior essay ability and rater adjustments, but the grade
  probabilities reflect the observed vote shares.
- **Fallback**: if data are too thin for the model or no strong majority exists,
  `PrincipledConsensusGrader` reports a Wilson-score interval and emits a warning
  so upstream services can request more ratings.

## Workflow

1. Prepare ratings (`essay_id`, `rater_id`, `grade`) using
   `ImprovedBayesianModel.prepare_data` or let the grader handle preprocessing.
2. Call `ImprovedBayesianModel.fit(...)` for analytic tasks or
   `PrincipledConsensusGrader.get_consensus(...)` for production usage.
3. Retrieve consensus grades via `get_consensus_grades()` or use the grader's
   per-essay `ConsensusResult` objects (grade, probabilities, confidence,
   confidence interval, method used, warning message).
4. Run `ModelValidator.run_full_validation(...)` during integration testing to
   confirm JA24 handling, majority alignment, bootstrap stability, and overall
   pass/fail status.

## Diagnostics & Stability

- ArviZ summaries run inside a targeted warning filter that suppresses the
  spurious "invalid value encountered in scalar divide" messages produced when
  chains collapse in sparse scenarios.
- Bootstrap stability runs on resampled datasets and maps posterior means back
  to the original essay/rater ordering, then scales coefficients of variation by
  the latent prior widths to avoid divide-by-zero artefacts.

## Usage Example

```python
import pandas as pd
from scripts.bayesian_consensus_model import (
    ImprovedBayesianModel,
    ModelConfig,
    PrincipledConsensusGrader,
)

# Fit the Bayesian model directly
ratings = pd.DataFrame(
    [
        {"essay_id": "EB01", "rater_id": "R001", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R002", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R003", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R004", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R005", "grade": "C"},
    ]
)
model = ImprovedBayesianModel(ModelConfig())
model.fit(ratings)
print(model.get_consensus_grades()["EB01"].consensus_grade)  # -> "B"

# Production-friendly consensus
grader = PrincipledConsensusGrader()
result = grader.get_consensus(ratings)["EB01"]
print(result.method_used)  # "weighted_majority"
print(result.confidence)   # 0.8 (4/5 majority)
```

## Testing

```
pdm run pytest scripts/bayesian_consensus_model/tests -q
```

The longest-running tests are the bootstrap stability checks in
`test_model_stability.py`; expect a 2–3 minute runtime on a laptop.

## Known Limitations & Next Steps

- The Bayesian mode still requires well-behaved posterior geometry; monitor
  ArviZ diagnostics and increase `target_accept` if divergences persist.
- Majority override is intentionally conservative (≥ 60 %); adjust the threshold
  only with product sign-off and update this document if you do.
- Hierarchical pooling of raters and essays remains future work once we collect
  more production data.

Document reviewed under HuleEdu documentation standard 090.
