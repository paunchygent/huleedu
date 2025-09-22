# Bayesian Consensus Grading Model

## Purpose & Scope

A statistically principled consensus grading system for Swedish national exam essays using Bayesian ordinal regression. The model aggregates multiple rater assessments into consensus grades while accounting for rater severity differences and quantifying confidence.

**⚠️ Critical Issue**: The model has a fundamental flaw causing incorrect consensus grades. See [README_FIRST.md](README_FIRST.md) for details.

## Architecture Overview

### Core Components

1. **Bayesian Model** (`bayesian_consensus_model.py`)
   - PyMC 5.10+ based ordinal regression with rater effects
   - Latent ability estimation for essays
   - Rater severity adjustments
   - Threshold estimation for grade boundaries
   - `ImprovedBayesianModel` class with adaptive MCMC sampling

2. **Production Grader** (`consensus_grading_solution.py`)
   - `PrincipledConsensusGrader` with hybrid approach
   - Uses Bayesian model when n_observations ≥ 50, n_essays ≥ 10, n_raters ≥ 5
   - Falls back to Wilson-score weighted majority voting for sparse data
   - Surfaces confidence intervals and method provenance

3. **Report Generator** (`generate_reports.py`)
   - Processes wide-format CSV rating data
   - Auto-detects v1 (comma) vs v2 (semicolon) format
   - Generates comprehensive output files

4. **Validator** (`model_validation.py`)
   - `ModelValidator` class for convergence and stability checks
   - Bootstrap validation and posterior diagnostics

## Stack & Versions

- **Python**: 3.11.11
- **Package Manager**: PDM 2.x
- **Key Dependencies** (from pyproject.toml):
  - `pymc >= 5.10.0` - Bayesian modeling
  - `numpy >= 1.24.0` - Numerical operations
  - `pandas >= 2.0.0` - Data manipulation
  - `scipy >= 1.11.0` - Statistical functions
  - `arviz >= 0.17.0` - MCMC diagnostics

## Swedish Grading Scale

The model uses 10 distinct ordinal levels (no plain E, D, or C grades exist):

```
F, F+, E-, E+, D-, D+, C-, C+, B, A
```

Mapped to numeric indices 0-9 for ordinal regression.

## How to Run

### Installation
```bash
# Install dependencies via PDM
pdm install
```

### Basic Usage
```bash
# Generate consensus grades from rating data
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv <input_csv_path> \
    --output-dir <output_directory> \
    --verbose

# Example with validated v2 data
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/consensus_results \
    --verbose
```

### Command Line Arguments
- `--ratings-csv`: Path to input CSV file (required)
- `--output-dir`: Directory for output files (required)
- `--sparse-threshold`: Min observations for Bayesian mode (default: 5)
- `--majority-threshold`: Min vote share for majority override (default: 0.6)
- `--use-production-grader`: Use PrincipledConsensusGrader
- `--verbose`: Print detailed progress information

### Output Files
Generated in the specified output directory:
- `essay_consensus.csv` - Final consensus grades with confidence scores
- `essay_grade_probabilities.csv` - Full probability distribution per essay
- `grade_thresholds.csv` - Estimated ordinal regression thresholds
- `rater_adjustments.csv` - Estimated rater severity parameters
- `model_diagnostics.json` - MCMC convergence metrics (rhat, ESS)

## Input Data Format

### V2 Format (Recommended)
Semicolon-delimited with header line to skip:
```csv
header_line_to_skip
ANCHOR-ID;FILE-NAME;Rater1;Rater2;Rater3;...
ES24;essay_file.docx;C+;B;C-;A;C+;C+
```

### V1 Format
Comma-delimited without header:
```csv
ANCHOR-ID,FILE-NAME,Rater1,Rater2,Rater3,...
ES24,essay_file.docx,C+,B,C-,A,C+,C+
```

The script auto-detects format based on delimiters in the file.

## Recent Decisions & Changes

### 2024-09-22: Swedish 10-Level Scale Implementation
- **Change**: Migrated from incorrect 6 base grades to full 10-level ordinal scale
- **Rationale**: Preserve meaningful distinctions between grades (C+ ≠ C-)
- **Files Updated**: All model files, tests, and consensus grading solution
- **Impact**: Grade modifiers now treated as distinct ordinal positions

### 2024-09-22: Critical Bug Identified
- **Issue**: Ordinal regression produces incorrect consensus for mixed ratings
- **Example**: ES24 gets C- instead of C+ despite 3/6 C+ votes
- **Root Cause**: OrderedLogistic likelihood weights all observations equally
- **Status**: Awaiting fix - model not suitable for production use

## Known Issues

### 🔴 Critical: Incorrect Consensus Calculation

The Bayesian model fails when essays have mixed ratings:

**Example - Essay ES24**:
- **Input**: C+ (×3), B (×1), A (×1), C- (×1)
- **Expected**: C+ (50% majority)
- **Actual**: C- with 81% confidence ❌

**Root Cause**:
```python
# The problematic likelihood in bayesian_consensus_model.py
eta = essay_ability[essay_idx] - rater_severity[rater_idx]
pm.OrderedLogistic("grade_obs", eta=eta, cutpoints=thresholds, observed=grades)
```

The OrderedLogistic likelihood:
1. Weights all observations equally
2. Finds compromise latent ability (1.52 for ES24)
3. Allows outliers to shift consensus from majority
4. Lacks robustness to genuine disagreement

**Impact**: Model unsuitable for production grading until fixed.

## Tests

```bash
# Run all unit tests
pdm run pytest scripts/bayesian_consensus_model/tests/test_model_core.py -v

# Current status: 60 tests passing
# Note: Tests verify mechanics but don't catch consensus correctness bug
```

## Project Structure

```
scripts/bayesian_consensus_model/
├── bayesian_consensus_model.py      # Core Bayesian model (bug is here)
├── consensus_grading_solution.py    # Production grader with fallback
├── generate_reports.py              # Report generation script
├── model_validation.py              # Validation utilities
├── anchor_essay_input_data/         # Input data directory
│   ├── eng_5_np_16_bayesian_assessment.csv     # V1 format
│   └── eng_5_np_16_bayesian_assessment_v2.csv  # V2 format (validated)
├── tests/
│   └── test_model_core.py          # Unit tests (60 passing)
├── README.md                        # This file
├── README_FIRST.md                  # Critical issue details
└── HANDOFF.md                       # Complete context for new sessions
```

## Development Notes

### Debugging the Consensus Issue
```python
# Quick check for ES24's grades
import pandas as pd
df = pd.read_csv('scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv',
                 sep=';', skiprows=1)
es24 = df[df['ANCHOR-ID'] == 'ES24']
print([g for g in es24.iloc[0][2:] if pd.notna(g) and g.strip()])
# Output: ['C+', 'B', 'C-', 'A', 'C+', 'C+']  <- C+ is majority
```

### Model Diagnostics
- Convergence warnings (rhat > 1.01) expected with current model issues
- Check `model_diagnostics.json` for detailed metrics
- Poor convergence likely symptom, not cause, of fundamental model flaw

### Next Steps for Fix
1. Replace OrderedLogistic with robust likelihood (e.g., Student-t)
2. Implement weighted observations based on rater agreement
3. Consider mixture model for heterogeneous disagreement
4. Or use majority voting as primary with Bayesian for uncertainty only

## References

- [PyMC Ordinal Regression](https://www.pymc.io/projects/docs/en/stable/api/distributions/discrete.html#pymc.distributions.discrete.OrderedLogistic)
- [Swedish National Exam Grading](https://www.skolverket.se/): F, F+, E-, E+, D-, D+, C-, C+, B, A
- See [HANDOFF.md](HANDOFF.md) for complete technical context

---
Document updated: 2024-09-22
Status: Model has critical bug - not production ready