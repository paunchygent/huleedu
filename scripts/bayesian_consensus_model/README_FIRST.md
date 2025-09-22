# 🚨 READ THIS FIRST - Bayesian Consensus Model

## Critical Issue: Model Produces Incorrect Consensus Grades

**Status**: The Bayesian ordinal regression model has a fundamental flaw that causes incorrect consensus grades.

### Example Failure Case (ES24)

**Actual Grades Received**:
- C+ (3 raters) - 50% majority
- B (1 rater)
- A (1 rater)
- C- (1 rater)

**Model Output**: C- with 81% confidence ❌
**Expected**: C+ (the majority grade) ✅

### Root Cause

The model's OrderedLogistic likelihood weights ALL observations equally when estimating a single latent ability:

```python
eta = essay_ability[essay_idx] - rater_severity[rater_idx]
pm.OrderedLogistic("grade_obs", eta=eta, cutpoints=thresholds, observed=grades)
```

This causes the model to:
1. Find a "compromise" latent ability that makes all grades somewhat probable
2. Allow outlier ratings (like the single C-) to pull consensus away from majority
3. Produce mathematically optimal but practically wrong results

### Quick Start

```bash
# Install dependencies (if not already done)
pdm install

# Run the model with sample data
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/test_results \
    --verbose

# Check the problematic output
cat output/test_results/essay_consensus.csv | grep ES24
# Shows: ES24 gets C- instead of C+
```

### Swedish Grading Scale

The model uses 10 ordinal grades (no plain E, D, or C):
```
F, F+, E-, E+, D-, D+, C-, C+, B, A
```

### Files You Need to Know

1. **Core Model**: `bayesian_consensus_model.py`
   - Line 446-456: The problematic OrderedLogistic likelihood
   - `get_consensus_grades()`: Where consensus is calculated

2. **Input Data**: `anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv`
   - Semicolon-delimited
   - Skip first line
   - Contains the ES24 test case

3. **Output**: `output/validated_10_scale/`
   - `essay_consensus.csv`: Shows wrong consensus for ES24
   - `essay_grade_probabilities.csv`: Shows incorrect probability distribution

### What Needs Fixing

The model needs one of:
1. **Robust likelihood** - Downweight outlier ratings
2. **Majority-aware consensus** - Respect the mode, not the compromise
3. **Mixture modeling** - Allow for genuine disagreement, not just severity differences

### DO NOT Try These (They Won't Work)

❌ Adjusting thresholds or priors
❌ Changing MCMC parameters
❌ Increasing sparse_data_threshold (just avoids using the model)

These are hacks that don't address the fundamental equal-weighting problem in the likelihood.

### Tests

```bash
# All 60 tests pass, but they don't catch the consensus problem
pdm run pytest scripts/bayesian_consensus_model/tests/test_model_core.py -v
```

---

**Next Step**: Fix the OrderedLogistic likelihood to handle outliers properly, or replace with a robust consensus mechanism.