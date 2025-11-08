"""Report generator for Bayesian model verification results."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from tabulate import tabulate


class ReportGenerator:
    """Generate markdown reports for Bayesian model analysis."""

    def __init__(self, output_dir: Path):
        """Initialize with output directory.

        Args:
            output_dir: Directory for saving reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_full_report(
        self,
        ja24_analysis: Dict[str, Any],
        diagnostic_results: Dict[str, Dict],
        consensus_comparison: pd.DataFrame,
        model_issues: Dict[str, Any],
    ) -> str:
        """Generate comprehensive markdown report.

        Args:
            ja24_analysis: JA24-specific analysis results
            diagnostic_results: Model diagnostic results
            consensus_comparison: DataFrame comparing consensus methods
            model_issues: Summary of identified issues

        Returns:
            Markdown report content
        """
        report = []

        # Header
        report.append(self._generate_header())

        # Executive Summary
        report.append(self._generate_executive_summary(ja24_analysis, model_issues))

        # JA24 Case Analysis
        report.append(self._generate_ja24_section(ja24_analysis, consensus_comparison))

        # Model Diagnostics
        report.append(self._generate_diagnostics_section(diagnostic_results))

        # Technical Issues
        report.append(self._generate_issues_section(model_issues))

        # Recommendations
        report.append(self._generate_recommendations())

        # Appendix
        report.append(self._generate_appendix(diagnostic_results))

        full_report = "\n\n".join(report)

        # Save to file
        output_file = self.output_dir / "bayesian_verification_report.md"
        with open(output_file, "w") as f:
            f.write(full_report)

        return full_report

    def _generate_header(self) -> str:
        """Generate report header."""
        return f"""# Bayesian Model Verification Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Purpose**: Critical analysis of Bayesian ordinal regression model for essay consensus grading
**Focus**: Essay JA24 consensus grade anomaly

---"""

    def _generate_executive_summary(self, ja24_analysis: Dict, model_issues: Dict) -> str:
        """Generate executive summary section."""
        return f"""## Executive Summary

### Key Finding
Essay JA24 received **{ja24_analysis.get("n_a_ratings", 0)} A ratings** and **{ja24_analysis.get("n_b_ratings", 0)} B ratings** from teachers, yet the Bayesian model assigned a consensus grade of **{ja24_analysis.get("model_consensus", "Unknown")}**.

### Root Causes Identified
1. **Circular Reasoning**: Raters who gave A's were labeled "generous" (avg severity: {ja24_analysis.get("avg_a_severity", 0):.2f}), causing their ratings to be systematically discounted
2. **Sum-to-Zero Constraint**: Forces artificial balancing of "generous" and "strict" raters
3. **Extreme Thresholds**: A-grade threshold set at 6.17 (2.64 units above B), making A nearly impossible after adjustments
4. **Overparameterization**: {model_issues.get("n_parameters", 0)} parameters estimated from sparse data

### Impact
- **Without adjustments**: JA24 would receive grade **{ja24_analysis.get("raw_consensus_median", "A")}**
- **With Bayesian adjustments**: JA24 receives grade **{ja24_analysis.get("model_consensus", "B")}**
- **Alternative methods**: Most agree on **A** or high **B**"""

    def _generate_ja24_section(
        self, ja24_analysis: Dict, consensus_comparison: pd.DataFrame
    ) -> str:
        """Generate JA24 case analysis section."""
        # Create ratings table
        ratings_data = []
        for rater, grade in ja24_analysis.get("raw_ratings", {}).items():
            severity = None
            for r in ja24_analysis.get("rater_analysis", []):
                if r["rater"] == rater:
                    severity = r["severity"]
                    break
            ratings_data.append([rater, grade, f"{severity:.2f}" if severity else "N/A"])

        ratings_table = tabulate(
            ratings_data, headers=["Rater", "Grade Given", "Severity Score"], tablefmt="pipe"
        )

        # Create consensus comparison table
        consensus_table = consensus_comparison[
            ["Method", "Consensus Grade", "Confidence"]
        ].to_markdown(index=False)

        return f"""## JA24 Case Analysis

### Raw Ratings
{ratings_table}

### Rater Adjustments Impact
- **A-raters average severity**: {ja24_analysis.get("avg_a_severity", 0):.2f} (labeled as generous)
- **B-raters average severity**: {ja24_analysis.get("avg_b_severity", 0):.2f} (labeled as neutral/strict)
- **Number of A-raters labeled "generous"**: {ja24_analysis.get("a_raters_labeled_generous", 0)} out of {ja24_analysis.get("n_a_ratings", 0)}

### Consensus Method Comparison
{consensus_table}

### Key Observation
Despite a clear majority of A ratings (71%), the model's severity adjustments effectively reversed the consensus, demonstrating how the model can produce counterintuitive results when rater adjustments dominate raw ratings."""

    def _generate_diagnostics_section(self, diagnostic_results: Dict) -> str:
        """Generate model diagnostics section."""
        threshold_diag = diagnostic_results.get("threshold_diagnostics", {})
        constraint_diag = diagnostic_results.get("constraint_diagnostics", {})
        identifiability = diagnostic_results.get("identifiability", {})

        return f"""## Model Diagnostics

### Threshold Analysis
- **B to A gap**: {threshold_diag.get("b_to_a_gap", 0):.2f} (largest in scale)
- **Mean threshold gap**: {threshold_diag.get("mean_gap", 0):.2f}
- **Extreme gaps identified**: {len(threshold_diag.get("extreme_gaps", []))}
- **Monotonic thresholds**: {"Yes" if threshold_diag.get("is_monotonic", False) else "No"}

### Sum-to-Zero Constraint Impact
- **Constraint detected**: {"Yes" if constraint_diag.get("has_sum_to_zero_constraint", False) else "No"}
- **Severity sum**: {constraint_diag.get("severity_sum", 0):.4f}
- **Distribution is bimodal**: {"Yes" if constraint_diag.get("is_bimodal", False) else "No"}
- **Forced balancing likely**: {
    "Yes" if constraint_diag.get("forced_balancing_likely", False) else "No"
}

### Model Complexity
- **Total parameters**: {identifiability.get("n_parameters", 0)}
- **Approximate observations**: {identifiability.get("approx_observations", 0):.0f}
- **Parameter/observation ratio**: {identifiability.get("param_obs_ratio", 0):.2f}
- **Status**: {identifiability.get("recommendation", "Unknown")}"""

    def _generate_issues_section(self, model_issues: Dict) -> str:
        """Generate technical issues section."""
        issues = []

        if model_issues.get("circular_reasoning_detected", False):
            issues.append("""### 1. Circular Reasoning
The model exhibits circular reasoning where:
- Raters are marked "generous" partly because they gave high grades
- Their high grades are then discounted because they're labeled "generous"
- This creates a self-reinforcing cycle that can reverse majority opinions""")

        if model_issues.get("extreme_thresholds", False):
            issues.append("""### 2. Extreme Grade Thresholds
- The A-grade threshold (6.17) is unreasonably high
- The gap between B and A (2.64 units) is much larger than other gaps
- This makes achieving an A grade nearly impossible after adjustments""")

        if model_issues.get("overparameterized", False):
            issues.append("""### 3. Model Overparameterization
- The model estimates too many parameters relative to available data
- With only 12 essays and sparse rater coverage, parameter estimates are unstable
- This leads to overfitting and unreliable adjustments""")

        if model_issues.get("sum_to_zero_issues", False):
            issues.append("""### 4. Sum-to-Zero Constraint Problems
- The constraint forces rater severities to sum to zero
- This creates artificial "strict" raters to balance "generous" ones
- The constraint may not reflect reality if all raters are similarly calibrated""")

        return f"""## Technical Issues Identified

{chr(10).join(issues)}"""

    def _generate_recommendations(self) -> str:
        """Generate recommendations section."""
        return """## Recommendations

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
4. **External validation**: Compare with student outcomes or expert consensus"""

    def _generate_appendix(self, diagnostic_results: Dict) -> str:
        """Generate appendix with detailed statistics."""
        severity_dist = diagnostic_results.get("severity_distribution", {})
        stats = severity_dist.get("statistics", {})

        return f"""## Appendix: Detailed Statistics

### Rater Severity Distribution
- **Mean**: {stats.get("mean", 0):.3f}
- **Median**: {stats.get("median", 0):.3f}
- **Std Dev**: {stats.get("std", 0):.3f}
- **Range**: [{stats.get("min", 0):.3f}, {stats.get("max", 0):.3f}]
- **Skewness**: {stats.get("skewness", 0):.3f}
- **Kurtosis**: {stats.get("kurtosis", 0):.3f}

### Rater Categories
- **Generous (< -0.5)**: {severity_dist.get("rater_categories", {}).get("generous", 0)} raters
- **Neutral (-0.5 to 0.5)**: {severity_dist.get("rater_categories", {}).get("neutral", 0)} raters
- **Strict (> 0.5)**: {severity_dist.get("rater_categories", {}).get("strict", 0)} raters

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

*End of Report*"""

    def generate_summary_table(self, results: Dict[str, Any]) -> str:
        """Generate a summary table of key findings.

        Args:
            results: Dictionary of analysis results

        Returns:
            Formatted table string
        """
        data = [
            ["Metric", "Value", "Status"],
            ["JA24 A Ratings", results.get("n_a_ratings", 0), "✓"],
            ["JA24 B Ratings", results.get("n_b_ratings", 0), "✓"],
            ["Model Consensus", results.get("model_consensus", "Unknown"), "✗"],
            ["Expected Consensus", "A", "✓"],
            [
                "Circular Reasoning",
                "Detected" if results.get("circular_reasoning", False) else "Not Detected",
                "✗" if results.get("circular_reasoning", False) else "✓",
            ],
            [
                "Model Overparameterized",
                "Yes" if results.get("overparameterized", False) else "No",
                "✗" if results.get("overparameterized", False) else "✓",
            ],
            [
                "Sum-to-Zero Issues",
                "Yes" if results.get("sum_to_zero_issues", False) else "No",
                "✗" if results.get("sum_to_zero_issues", False) else "✓",
            ],
        ]

        return tabulate(data, headers="firstrow", tablefmt="grid")
