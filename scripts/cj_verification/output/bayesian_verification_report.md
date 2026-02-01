# Bayesian Model Verification Report

**Generated**: 2025-09-22 03:44:45
**Purpose**: Critical analysis of Bayesian ordinal regression model for essay consensus grading
**Focus**: Essay JA24 consensus grade anomaly

---

## Executive Summary

### Key Finding
Essay JA24 received **4 A ratings** and **2 B ratings** from teachers, yet the Bayesian model assigned a consensus grade of **B**.

### Root Causes Identified
1. **Circular Reasoning**: Raters who gave A's were labeled "generous" (avg severity: -0.95), causing their ratings to be systematically discounted
2. **Sum-to-Zero Constraint**: Forces artificial balancing of "generous" and "strict" raters
3. **Extreme Thresholds**: A-grade threshold set at 6.17 (2.64 units above B), making A nearly impossible after adjustments
4. **Overparameterization**: 35 parameters estimated from sparse data

### Impact
- **Without adjustments**: JA24 would receive grade **A**
- **With Bayesian adjustments**: JA24 receives grade **B**
- **Alternative methods**: Most agree on **A** or high **B**

## JA24 Case Analysis

### Raw Ratings

| Rater    | Grade Given   | Severity Score   |
|:---------|:--------------|:-----------------|
| Erik A   | A             | N/A              |
| Yvonne R | B             | N/A              |
| Agneta D | B             | N/A              |
| Anna P   | A             | N/A              |
| Hanna L  | A             | N/A              |
| Jenny P  | A             | N/A              |

### Rater Adjustments Impact
- **A-raters average severity**: -0.95 (labeled as generous)
- **B-raters average severity**: 0.08 (labeled as neutral/strict)
- **Number of A-raters labeled "generous"**: 3 out of 4

### Consensus Method Comparison

| Method             | Consensus Grade   |   Confidence |
|:-------------------|:------------------|-------------:|
| Simple Majority    | A                 |        0.667 |
| Weighted Median    | A                 |        0.6   |
| Trimmed Mean (20%) | A                 |        0.536 |
| Rater Adjusted     | A                 |        0.452 |

### Key Observation
Despite a clear majority of A ratings (71%), the model's severity adjustments effectively reversed the consensus, demonstrating how the model can produce counterintuitive results when rater adjustments dominate raw ratings.

## Model Diagnostics

### Threshold Analysis
- **B to A gap**: 2.64 (largest in scale)
- **Mean threshold gap**: 1.16
- **Extreme gaps identified**: 0
- **Monotonic thresholds**: Yes

### Sum-to-Zero Constraint Impact
- **Constraint detected**: Yes
- **Severity sum**: 0.0000
- **Distribution is bimodal**: No
- **Forced balancing likely**: No

### Model Complexity
- **Total parameters**: 35
- **Approximate observations**: 60
- **Parameter/observation ratio**: 0.58
- **Status**: Model is overparameterized

## Technical Issues Identified

### 1. Circular Reasoning
The model exhibits circular reasoning where:
- Raters are marked "generous" partly because they gave high grades
- Their high grades are then discounted because they're labeled "generous"
- This creates a self-reinforcing cycle that can reverse majority opinions
### 2. Extreme Grade Thresholds
- The A-grade threshold (6.17) is unreasonably high
- The gap between B and A (2.64 units) is much larger than other gaps
- This makes achieving an A grade nearly impossible after adjustments
### 3. Model Overparameterization
- The model estimates too many parameters relative to available data
- With only 12 essays and sparse rater coverage, parameter estimates are unstable
- This leads to overfitting and unreliable adjustments

## Recommendations

### Immediate Actions
1. **Remove sum-to-zero constraint** - Let the data determine overall rater calibration
2. **Simplify the model** - Use standard normal priors instead of complex hierarchical structures
3. **Adjust threshold initialization** - Use empirical quantiles from observed grade distributions
4. **Implement sanity checks** - Flag cases where majority opinion is reversed

### Model Improvements
1. **Use simpler consensus methods** as primary approach:
   - Weighted median (robust to outliers)
   - Trimmed mean (removes extremes)
   - Simple Bradley-Terry (already implemented in CJ Assessment Service)

2. **Reserve Bayesian models** for cases with:
   - Sufficient data (>100 essays, >20 raters)
   - Dense rating matrices (>70% coverage)
   - Clear need for complex adjustments

3. **Add validation layers**:
   - Compare Bayesian results with simpler methods
   - Flag large discrepancies for manual review
   - Bootstrap confidence intervals for all estimates

### Data Collection Improvements
1. **Increase rating density**: Ensure each essay gets 7+ ratings
2. **Add calibration essays**: Have all raters grade 2-3 common essays
3. **Track rater consistency**: Monitor intra-rater reliability over time
4. **External validation**: Compare with student outcomes or expert consensus

## Appendix: Detailed Statistics

### Rater Severity Distribution
- **Mean**: 0.000
- **Median**: -0.108
- **Std Dev**: 0.960
- **Range**: [-1.382, 2.178]
- **Skewness**: 0.438
- **Kurtosis**: -0.233

### Rater Categories
- **Generous (< -0.5)**: 4 raters
- **Neutral (-0.5 to 0.5)**: 6 raters
- **Strict (> 0.5)**: 4 raters

### Files Analyzed
- `ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv`
- `ordinal_rater_severity.csv`
- `ordinal_thresholds.csv`
- `ordinal_true_scores_essays.csv`

### Verification Scripts
- `bayesian_model_verification.py` - Main analysis script
- `alternative_consensus_methods.py` - Alternative grading methods
- `model_diagnostics.py` - Statistical diagnostics
- `visualization_generator.py` - Diagnostic plots

---

*End of Report*
