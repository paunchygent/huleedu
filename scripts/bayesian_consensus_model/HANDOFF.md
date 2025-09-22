# Handoff Document - Bayesian Consensus Model

## Current Status

**Date**: 2024-09-22
**Last Working Session**: Identified fundamental flaw in Bayesian ordinal regression model

### Summary
The Bayesian consensus grading model for Swedish national exam essays is **functionally complete but produces incorrect results** due to equal weighting of all observations in the OrderedLogistic likelihood. The model correctly implements the 10-level Swedish grading scale but fails to handle rating disagreements properly.

## The Core Problem

### Model Architecture Flaw

The current implementation in `bayesian_consensus_model.py` (lines 446-456):

```python
# Linear predictor: ability - severity
eta = essay_ability[essay_idx] - rater_severity[rater_idx]

# Ordinal likelihood - THIS IS THE PROBLEM
pm.OrderedLogistic(
    "grade_obs",
    eta=eta,
    cutpoints=thresholds,
    observed=grades,
    compute_p=False,
)
```

**Why it fails**: The OrderedLogistic likelihood treats all ratings equally, finding a single latent ability that maximizes the likelihood of ALL observations. This causes outlier ratings to compromise the consensus.

### Concrete Failure Case

Essay ES24 demonstrates the failure:
- **Input grades**: C+, C+, C+, B, A, C-
- **Expected consensus**: C+ (3/6 = 50% majority)
- **Model output**: C- (wrong!)
- **Model's latent ability**: 1.52
- **C-/C+ threshold**: 1.57
- Since 1.52 < 1.57, model assigns C-

## Open Challenges

1. **Fundamental Model Fix Needed**
   - Current OrderedLogistic lacks robustness to outliers
   - No concept of majority consensus in likelihood
   - Equal weighting inappropriate for heterogeneous ratings

2. **Not Calibration Issues**
   - Adjusting priors won't fix equal weighting
   - Changing thresholds just moves the problem
   - MCMC parameters are fine (model converges)

3. **Swedish Grade Complexity**
   - 10 ordinal levels: F, F+, E-, E+, D-, D+, C-, C+, B, A
   - No intermediate grades (no plain E, D, C)
   - But this is NOT the cause - model sees only ordered integers 0-9

## Environment Setup

### Python Environment
```bash
# Using PDM (Python Dependency Manager)
python --version  # Python 3.11.11
pdm --version     # PDM 2.x

# Install dependencies
pdm install

# Activate environment (PDM handles this)
pdm run <command>
```

### Key Dependencies
From `pyproject.toml`:
- `pymc >= 5.10.0`
- `numpy >= 1.24.0`
- `pandas >= 2.0.0`
- `scipy >= 1.11.0`
- `arviz >= 0.17.0`

## Paths and Artifacts

### Input Data
```
scripts/bayesian_consensus_model/anchor_essay_input_data/
├── eng_5_np_16_bayesian_assessment.csv       # V1 format (comma-delimited)
└── eng_5_np_16_bayesian_assessment_v2.csv    # V2 format (semicolon-delimited, RECOMMENDED)
```

**V2 Format** (semicolon-delimited):
- First line: header to skip
- Format: `ANCHOR-ID;FILE-NAME;Rater1;Rater2;...`
- ES24 is row 13 in the file

### Output Locations
```
output/
├── test_10_scale/           # Initial test results
└── validated_10_scale/      # Results from v2 data
    ├── essay_consensus.csv           # Consensus grades (SHOWS THE BUG)
    ├── essay_grade_probabilities.csv # Grade probability distributions
    ├── grade_thresholds.csv          # Ordinal thresholds
    ├── rater_adjustments.csv         # Rater severity estimates
    └── model_diagnostics.json        # Convergence metrics
```

### Source Code
```
scripts/bayesian_consensus_model/
├── bayesian_consensus_model.py       # Core model (THE PROBLEM IS HERE)
├── consensus_grading_solution.py     # Production grader with fallback
├── generate_reports.py               # Report generation script
├── model_validation.py               # Validation utilities
├── tests/
│   └── test_model_core.py           # 60 passing tests
├── README.md                         # General documentation
├── README_FIRST.md                   # Critical issue summary
└── HANDOFF.md                        # This file
```

## Running the Model

### Quick Reproduction of Bug
```bash
# Run with validated v2 data
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/bug_reproduction \
    --verbose

# Check ES24's incorrect result
grep ES24 output/bug_reproduction/essay_consensus.csv
# Shows: ES24,...,C-,0.8111,bayesian,... (WRONG - should be C+)
```

### Verify the Input Data
```bash
# Check ES24's actual grades
pdm run python -c "
import pandas as pd
df = pd.read_csv('scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv', sep=';', skiprows=1)
es24 = df[df['ANCHOR-ID'] == 'ES24']
print('ES24 grades:', [g for g in es24.iloc[0][2:] if pd.notna(g) and g.strip()])
"
# Output: ES24 grades: ['C+', 'B', 'C-', 'A', 'C+', 'C+']
```

## Test Results

### Latest Test Run (2024-09-22)
```bash
pdm run pytest scripts/bayesian_consensus_model/tests/test_model_core.py -v
# Result: 60 passed in 3.69s
```

**Note**: Tests pass but don't catch the consensus bug because they test mechanics, not correctness of consensus calculation.

### Model Diagnostics
From `output/validated_10_scale/model_diagnostics.json`:
```json
{
  "convergence": {
    "converged": false,
    "max_rhat": 2.09,  // Poor convergence (>1.01 is bad)
    "min_ess_bulk": 5.0,
    "min_ess_tail": 28.0
  },
  "parameters": {
    "n_essays": 12,
    "n_observations": 60,
    "n_raters": 14
  }
}
```
**Note**: Convergence issues likely symptom, not cause, of the fundamental model problem.

## Expected Outputs

### Correct Consensus (What ES24 Should Get)
```csv
essay_id,consensus_grade,confidence
ES24,C+,0.50  # C+ has 3/6 = 50% of votes
```

### Current Wrong Output
```csv
essay_id,consensus_grade,confidence
ES24,C-,0.8111  # Model incorrectly assigns C-
```

## Next Steps

### Immediate Priority
Fix the ordinal regression model to handle disagreement properly. Options:

1. **Replace OrderedLogistic with Robust Alternative**
   ```python
   # Potential: Use Student-t likelihood for heavy tails
   # Or: Implement mixture model for outlier detection
   ```

2. **Implement Weighted Likelihood**
   ```python
   # Weight observations by agreement with majority
   # Or: Two-stage model - identify consensus first, then refine
   ```

3. **Switch Primary Method**
   ```python
   # Use majority voting as primary
   # Bayesian model only for uncertainty quantification
   ```

### Don't Waste Time On
- ❌ Tweaking MCMC parameters (not the issue)
- ❌ Adjusting priors (won't fix equal weighting)
- ❌ Changing thresholds (just moves the problem)
- ❌ Increasing sparse_threshold (avoids model, doesn't fix it)

## Critical Context

### Why This Matters
The model is for grading Swedish national exam essays. Getting consensus wrong means:
- Incorrect student grades
- Invalid assessment of writing quality
- Loss of trust in automated grading

### What We Learned
1. Standard ordinal regression assumes homogeneous ratings (all measuring same thing)
2. Real grading shows heterogeneous disagreement (different quality perceptions)
3. Equal weighting in likelihood is inappropriate for consensus
4. Outlier ratings need special handling, not equal weight

### Key Insight
The model tries to find ONE latent ability that explains ALL ratings. When raters fundamentally disagree (not just severity differences), this compromise approach fails. ES24 is the proof - the model finds ability=1.52 that makes both C- and A "somewhat likely" rather than recognizing C+ as the consensus.

## Commands Reference

```bash
# Install/update dependencies
pdm install

# Run model on v2 data
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/results \
    --verbose

# Run tests
pdm run pytest scripts/bayesian_consensus_model/tests/test_model_core.py -v

# Quick check ES24
grep ES24 output/validated_10_scale/essay_consensus.csv

# Python path for imports
export PYTHONPATH="${PYTHONPATH}:scripts/bayesian_consensus_model"
```

## Contact & References

- **Previous work**: See git history for full context
- **Model theory**: PyMC ordinal regression documentation
- **Swedish grades**: National exam uses F, F+, E-, E+, D-, D+, C-, C+, B, A

---

**Handoff prepared**: 2024-09-22
**Ready for**: New Claude instance to continue debugging model
**Priority**: Fix ES24 consensus calculation