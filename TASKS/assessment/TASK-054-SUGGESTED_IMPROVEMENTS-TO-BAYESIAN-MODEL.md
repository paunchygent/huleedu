---
id: 'TASK-054-SUGGESTED_IMPROVEMENTS-TO-BAYESIAN-MODEL'
title: 'Existing'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-25'
last_updated: '2025-11-17'
related: []
labels: []
---
## Bayesian Consensus Model Improvement Plan

### Understanding Summary

#### Current System

- **Grade Scale**: Swedish 10-grade scale (`F`, `F+`, `E-`, `E+`, `D-`, `D+`, `C-`, `C+`, `B`, `A`)
- **Raters**: Fourteen teachers (`B01`–`B14`) with sparse participation
- **Model**: Gaussian kernel smoothing with empirical Bayes bias correction
- **Issues**: Inconsistent decision rule, uncalibrated confidence, data leakage, and missing quality control

#### Key Improvements from `TASK-054`

1. **Argmax Decision Rule** instead of rounding
2. **Leave-One-Out Essay Means** to prevent leakage
3. **Precision-Aware Weighting** using bias variance
4. **Neutral-ESS Metrics** for quality control visibility

### Implementation Plan

#### 1. Enhanced Configuration System (`scripts/bayesian_consensus_model/models/ordinal_kernel.py`)

```python
@dataclass
class KernelConfig:
    # Existing
    sigma: float = 0.85
    pseudo_count: float = 0.02
    severity: RaterSeverityConfig | None = None
    bias_correction: bool = True

    # New modular improvements
    use_argmax_decision: bool = False       # A: Argmax vs rounding
    use_loo_alignment: bool = False         # B: Leave-one-out
    use_precision_weights: bool = False     # C: Variance-aware
    use_neutral_gating: bool = False        # D: Quality control

    # Neutral evidence parameters
    neutral_delta_mu: float = 0.25
    neutral_var_max: float = 0.20
```

#### 2. Leave-One-Out Alignment (Fix B) (`scripts/bayesian_consensus_model/models/rater_severity.py`)

- **Add** `compute_loo_deviations()`:
  - Calculate essay means excluding the focal rater
  - Return deviations for alignment and empirical Bayes calculations
- **Modify** `compute_rater_weights()` to optionally use LOO deviations
- **Modify** `compute_rater_bias_posteriors_eb()` to optionally use LOO deviations

#### 3. Decision Rule Enhancement (Fix A) (`scripts/bayesian_consensus_model/models/ordinal_kernel.py`)

- Update `consensus()` to:
  - Switch between argmax and rounding based on configuration
  - Preserve both paths for comparative evaluation

#### 4. Precision-Aware Weighting (Fix C) (`scripts/bayesian_consensus_model/models/rater_severity.py`)

- **Create** `apply_precision_weights()`:
  - Input baseline weights and bias posteriors
  - Apply precision factor `1 / (var_post + eps)`
  - Optionally penalize large bias magnitudes
- Integrate precision factors into the primary weight computation

#### 5. Neutral Evidence Metrics (Fix D) (`scripts/bayesian_consensus_model/models/ordinal_kernel.py`)

- **Add** `compute_neutral_ess()`:
  - Classify neutral raters using bias and variance thresholds
  - Compute the effective sample size of neutral evidence
- Extend consensus results to include:
  - `neutral_ess`
  - `needs_more_ratings`

#### 6. Comprehensive Test Harness (`scripts/bayesian_consensus_model/tests/test_improvements.py`)

- Add `TestImprovements` with:
  - `test_argmax_vs_rounding()`
  - `test_loo_alignment_effect()`
  - `test_precision_weighting()`
  - `test_neutral_metrics()`
  - `test_combined_improvements()`

`scripts/bayesian_consensus_model/evaluation/harness.py`

- Implement `ImprovementHarness`:
  - `run_ablation_study()` for per-feature impact
  - `compare_configurations()` for A/B testing
  - `generate_metrics()` for accuracy and overturn analysis
  - `create_report()` for detailed summaries

#### 7. Comparison Pipeline (`scripts/bayesian_consensus_model/evaluation/compare_models.py`)

- Load anchor essay datasets
- Execute baseline and improved models
- Generate metrics for:
  - Consensus changes
  - Confidence calibration
  - Overturn rates
  - Neutral evidence coverage

### Implementation Order

1. **Phase 1: Infrastructure (Day 1)**
   - Extend `KernelConfig` with feature flags
   - Scaffold evaluation harness
   - Introduce required fixtures
2. **Phase 2: Core Fixes (Days 2–3)**
   - Implement leave-one-out alignment (Fix B)
   - Add argmax decision rule (Fix A)
   - Write isolated unit tests
3. **Phase 3: Advanced Features (Days 4–5)**
   - Implement precision-aware weighting (Fix C)
   - Add neutral-ESS metrics (Fix D)
   - Expand integration tests
4. **Phase 4: Evaluation (Day 6)**
   - Run ablation studies
   - Produce comparison reports
   - Document findings

### Testing Strategy

#### Unit Tests

- **Isolation**: Verify each improvement individually
- **Accuracy**: Confirm mathematical correctness
- **Robustness**: Cover critical edge cases

#### Integration Tests

- **Combined Behavior**: Validate interactions among improvements
- **Real Data**: Exercise anchor essay datasets
- **Performance**: Monitor execution and throughput impacts

### Evaluation Metrics

- **Accuracy**: Agreement with expert consensus
- **Stability**: Repeatability across runs
- **Coverage**: Fraction of essays requiring additional ratings
- **Calibration**: Confidence alignment with actual accuracy

### Configuration Examples

```python
# Baseline
baseline_config = KernelConfig(
    sigma=0.85,
    bias_correction=True,
    use_argmax_decision=False,
    use_loo_alignment=False,
)

# Full improvements
improved_config = KernelConfig(
    sigma=0.85,
    bias_correction=True,
    use_argmax_decision=True,
    use_loo_alignment=True,
    use_precision_weights=True,
    use_neutral_gating=True,
    neutral_min_ess=2.5,
)
```

### Success Criteria

- **Modularity**: Each improvement is independently toggleable
- **Backwards Compatibility**: Baseline behavior preserved when flags are off
- **Performance**: Fewer than 10% of essays require additional ratings
- **Accuracy**: Improved agreement with expert consensus
- **Documentation**: Clear guidance for parameters and usage

---

This plan delivers modular, testable enhancements that enable comparative analysis of every change without sacrificing the existing workflow.
