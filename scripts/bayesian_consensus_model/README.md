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
- `--ratings-csv`: Path to the long-format ratings CSV (required)
- `--output-dir`: Directory for run artifacts (default: `output/bayesian_consensus_model`)
- `--verbose`: Print progress information
- `--bias-correction`: Toggle empirical-Bayes bias adjustment (`on`/`off`, default `on`)
- `--compare-without-bias`: Emit paired runs with and without bias correction
- `--run-label`: Optional label for the output directory
- `--use-argmax-decision`: Select the highest-probability grade instead of rounding the expectation
- `--use-loo-alignment`: Enable leave-one-out alignment for severity weights and bias posteriors
- `--use-precision-weights`: Down-weight raters with high posterior uncertainty or large bias magnitude
- `--use-neutral-gating`: Compute neutral ESS per essay (informational only)
- `--neutral-delta-mu`: Absolute posterior bias threshold for “neutral” raters (default `0.25`)
- `--neutral-var-max`: Posterior variance ceiling for neutral raters (default `0.20`)

### Output Files
Generated in the specified output directory:
- `essay_consensus.csv` – Consensus grade, confidence, expected grade index, and neutral ESS (flag retained for compatibility but no longer auto-gates)
- `essay_grade_probabilities.csv` – Full posterior mass over the 10-grade lattice
- `rater_weights.csv` / `rater_severity.csv` / `rater_agreement.csv` / `rater_spread.csv` – Severity diagnostics and precision factors
- `rater_bias_posteriors_eb.csv` – Empirical-Bayes bias mean, variance, shrinkage, and neutral classification inputs
- `essay_inter_rater_stats.csv` – Entropy, spread, and neutral ESS per essay
- `model_diagnostics.json` – Serialized `KernelConfig` including feature toggles and hyperparameters
- `rater_bias_vs_weight.png` – Optional visualization (requires Matplotlib)

## Modular Improvements (What & Why)

| Feature | What It Does | Why It Matters |
| --- | --- | --- |
| `use_argmax_decision` | Chooses the grade with the highest posterior probability instead of rounding the expected index. | Prevents bimodal distributions from collapsing to the lower neighbour when the posterior mass is skewed upward, aligning the reported grade with the modal support. |
| `use_loo_alignment` | Removes the focal rater before recomputing essay means for alignment, weights, and bias posteriors. | Eliminates self-influence when panels are sparse, tightening bias estimates and reducing false generosity penalties on high-volume raters. |
| `use_precision_weights` | Multiplies reliability weights by inverse posterior variance and dampens large absolute bias. | Encourages the model to trust raters whose bias is estimated precisely while down-weighting noisy or extreme raters, improving robustness under disagreement. |
| `use_neutral_gating` | Classifies neutral raters and tracks their effective sample size per essay. | Provides neutral ESS visibility for coordinators without enforcing automatic gates. |

Set these toggles via the CLI flags listed above or by instantiating `KernelConfig` directly.

## Evaluation Harness

Use `scripts/bayesian_consensus_model/evaluation/harness.py` to quantify each improvement in isolation. The harness:

- Loads the same long-format ratings used by the CLI.
- Runs configurable `KernelConfig` baselines and toggled variants.
- Reports grade changes, confidence deltas, and neutral ESS coverage (informational only).

## D-Optimal Pair Scheduling & Redistribution

Use the optimizer utilities to generate comparison schedules with maximal Fisher information for CJ sessions, then feed the output straight into the redistribution tools.

### Prototype script (legacy)

```bash
# 84-slot optimization for Session 2 (improves log-det from 33.98 → 37.67)
python scripts/bayesian_consensus_model/d_optimal_prototype.py \
  --mode session2 \
  --output scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs_optimized.csv

# 149-slot expansion (target ~150 comparisons for 24 essays)
python scripts/bayesian_consensus_model/d_optimal_prototype.py \
  --mode session2 \
  --total-slots 149 \
  --output scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs_optimized_149.csv
```

- `--max-repeat` controls how many times any ordered pair may appear (default `3`).
- Use `--mode synthetic --total-slots <n>` to sanity-check behaviour on mock data.

### Typer CLI workflow

```bash
# Session-driven optimization with diagnostics + JSON report
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --pairs-csv scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs.csv \
  --output-csv scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs_optimized.csv \
  --include-status core \
  --total-slots 84 \
  --max-repeat 3 \
  --report-json output/d_optimal/session2_84.json

# Same run but sourcing comparisons from a prepared JSON payload
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --baseline-json output/session2_baseline_payload.json \
  --output-csv scripts/bayesian_consensus_model/session_2_planning/20251027-143747/session2_pairs_optimized.json.csv \
  --total-slots 84 \
  --max-repeat 3

# Synthetic smoke test
python -m scripts/bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --mode synthetic \
  --total-slots 36 \
  --max-repeat 3 \
  --output-csv output/d_optimal/synthetic_36.csv
```

The CLI prints baseline/optimized log-determinant, comparison-type distributions, per-student anchor coverage, and any repeated pairs (respecting the configured `--max-repeat`). Use `--report-json` for machine-readable diagnostics to slot into notebooks/pipelines.

### Textual TUI

Run `python scripts/bayesian_consensus_model/redistribute_tui.py` for an interactive flow:

- Fill in pair/assignment paths, then set optimization parameters (`total slots`, `max repeat`, status pool). The
  **Optional Baseline JSON Path** field accepts the same payload format as `--baseline-json` for browser/API handoff.
- Press `o` (or click **Optimize**) to regenerate a schedule; the optimizer summary is streamed to the log and the pairs path updates automatically.
- Toggle “Optimize before assigning?” to run the optimizer every time you press `g`/Generate so redistribution always consumes the fresh schedule.

### Optimization guarantees

- Anchor adjacency comparisons (each anchor compares with its neighbours at least once).
- Student bracket coverage derived from the baseline plan (below/near/above anchors per student).
- Slot budgets so you can align with 84 vs 149+ comparison targets.

### Balanced redistribution

`redistribute_core.assign_pairs` now performs type-aware balancing so every rater receives at least one student-anchor comparison (when available) and a mixed workload across comparison types—no more anchor-only chunks unless the pool truly lacks student essays. When the requested workload exceeds the available pool, the CLI/TUI auto-scale per-rater quotas, emit a shortage notice, and export the exact number of feasible assignments. Regression tests lock in both the balancing and shortage handling behaviours.

Generated CSVs retain the `pair_id, essay_*` schema, so downstream tooling consuming `redistribute_core.write_assignments` continues to work unchanged.

### Troubleshooting

- **“No remaining slots after applying locked constraints.”** Increase `--total-slots` so the budget covers anchor adjacency (`len(anchor_order) - 1`) plus student bracket requirements, or include more baseline comparisons (`--include-status all`).
- **Missing anchor coverage warnings.** Inspect the listed students, then bump `--total-slots` or revisit the baseline CSV to ensure each student has three anchor brackets available.
- **Repeat count violation.** Lower `--max-repeat` or prune locked pairs in the baseline before rerunning; the CLI summary lists offending pairs.

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

### 2025-01-25: Modular Ordinal Kernel Enhancements
- **Change**: Added configurability for argmax decision rule, leave-one-out alignment, precision-aware weighting, and neutral ESS metrics (no automatic gating)
- **Evaluation**: `scripts/bayesian_consensus_model/evaluation/harness.py` provides ablation studies and comparative metrics
- **Outputs**: Consensus CSVs now include `neutral_ess` (informational) and backward-compatible `needs_more_ratings`

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
