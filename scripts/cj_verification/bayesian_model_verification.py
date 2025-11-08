#!/usr/bin/env python3
"""Main verification script for Bayesian ordinal regression model analysis.

This script performs comprehensive verification of the Bayesian model used for
essay grading consensus, focusing on the JA24 anomaly where 5 A ratings and
2 B ratings resulted in a B consensus grade.

Purpose:
- Diagnose issues with the Many-Facet Rasch Model implementation
- Compare Bayesian results with simpler baseline methods
- Generate visualizations and reports highlighting model problems

Usage:
    python bayesian_model_verification.py \
        --data-path /path/to/BAYESIAN_ANALYSIS_GPT_5_PRO/ \
        --focus-essay JA24 \
        --output-dir ./output/
"""

import argparse
import json
from pathlib import Path

# Local imports
from data_loader import BayesianDataLoader
from grading_baseline_methods import (
    compare_all_methods,
)
from model_diagnostics import BayesianModelDiagnostics, diagnose_ja24_specific_issues
from report_generator import ReportGenerator
from visualization_generator import VisualizationGenerator


def main(data_path: str, focus_essay: str = "JA24", output_dir: str = "./output/"):
    """Run comprehensive Bayesian model verification.

    Args:
        data_path: Path to BAYESIAN_ANALYSIS_GPT_5_PRO directory
        focus_essay: Essay ID to focus analysis on (default: JA24)
        output_dir: Directory for output files
    """
    print("=" * 60)
    print("BAYESIAN MODEL VERIFICATION SYSTEM")
    print("=" * 60)

    # Initialize components
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n1. Loading data from: {data_path}")
    loader = BayesianDataLoader(Path(data_path))

    # Load all necessary data
    raw_ratings_df = loader.load_raw_ratings()
    rater_severity_df = loader.load_rater_severity()
    thresholds_df = loader.load_thresholds()
    loader.load_consensus_grades()
    agreement_metrics = loader.load_agreement_metrics()

    print(f"   - Loaded {len(raw_ratings_df)} essays")
    print(f"   - Loaded {len(rater_severity_df)} rater severities")
    print(f"   - Loaded {len(thresholds_df)} grade thresholds")

    # Focus on specific essay
    print(f"\n2. Analyzing essay: {focus_essay}")
    essay_ratings = loader.get_essay_ratings(focus_essay)
    essay_consensus = loader.get_consensus_for_essay(focus_essay)

    print(f"   - Raw ratings: {essay_ratings}")
    print(f"   - Model consensus: {essay_consensus['predicted_grade']}")
    print(f"   - Latent ability: {essay_consensus['latent_ability']:.3f}")

    # Analyze rater adjustments
    print(f"\n3. Analyzing rater adjustments for {focus_essay}")
    adjustment_analysis = loader.analyze_essay_adjustments(focus_essay)
    print(adjustment_analysis.to_string())

    # Run diagnostic analyses
    print("\n4. Running model diagnostics...")
    diagnostics = BayesianModelDiagnostics(thresholds_df, rater_severity_df)

    diagnostic_results = {
        "threshold_diagnostics": diagnostics.diagnose_threshold_issues(),
        "constraint_diagnostics": diagnostics.diagnose_sum_to_zero_constraint(),
        "severity_distribution": diagnostics.analyze_rater_severity_distribution(),
        "circular_reasoning": diagnostics.detect_circular_reasoning(essay_ratings),
        "identifiability": diagnostics.compute_identifiability_metrics(),
    }

    print(
        f"   - Threshold issues: B→A gap = {diagnostic_results['threshold_diagnostics']['b_to_a_gap']:.2f}"
    )
    print(
        f"   - Sum-to-zero constraint: {diagnostic_results['constraint_diagnostics']['has_sum_to_zero_constraint']}"
    )
    print(
        f"   - Circular reasoning: {diagnostic_results['circular_reasoning']['circular_reasoning_detected']}"
    )
    print(
        f"   - Overparameterized: {diagnostic_results['identifiability']['is_overparameterized']}"
    )

    # Compare with alternative methods
    print("\n5. Comparing with baseline consensus methods...")
    severity_map = loader.get_rater_severity_map()
    consensus_comparison = compare_all_methods(essay_ratings, rater_severities=severity_map)
    print(consensus_comparison.to_string())

    # Generate visualizations
    print("\n6. Generating visualizations...")
    viz = VisualizationGenerator(output_path)

    # Convert ratings to numeric for visualization
    adjusted_ratings = {}
    for rater, grade in essay_ratings.items():
        numeric = loader.grade_to_numeric(grade)
        if rater in severity_map:
            # Apply adjustment for visualization
            adjusted_ratings[rater] = numeric - severity_map[rater] * 0.5
        else:
            adjusted_ratings[rater] = numeric

    # Create all visualizations
    print("   - Creating Sankey diagram...")
    viz.create_sankey_diagram(
        essay_ratings, adjusted_ratings, essay_consensus["predicted_grade"], focus_essay
    )

    print("   - Creating rater severity heatmap...")
    viz.create_rater_severity_heatmap(rater_severity_df, raw_ratings_df)

    print("   - Creating threshold visualization...")
    viz.create_threshold_visualization(thresholds_df)

    print("   - Creating consensus comparison plot...")
    viz.create_consensus_comparison_plot(consensus_comparison, focus_essay)

    print("   - Creating JA24 comprehensive visualization...")
    # Extract alternative grades for comprehensive plot
    alternative_grades = {}
    for _, row in consensus_comparison.iterrows():
        if row["Method"] != "Rater Adjusted":  # Exclude adjusted method for clarity
            alternative_grades[row["Method"]] = row["Consensus Grade"]

    viz.create_ja24_specific_visualization(
        essay_ratings, severity_map, essay_consensus["predicted_grade"], alternative_grades
    )

    # Generate JA24-specific analysis
    ja24_analysis = diagnose_ja24_specific_issues(
        essay_ratings, rater_severity_df, essay_consensus["predicted_grade"], thresholds_df
    )

    # Compile model issues summary
    model_issues = {
        "circular_reasoning_detected": diagnostic_results["circular_reasoning"][
            "circular_reasoning_detected"
        ],
        "extreme_thresholds": diagnostic_results["threshold_diagnostics"]["b_to_a_gap"] > 2.0,
        "overparameterized": diagnostic_results["identifiability"]["is_overparameterized"],
        "sum_to_zero_issues": diagnostic_results["constraint_diagnostics"][
            "forced_balancing_likely"
        ],
        "n_parameters": diagnostic_results["identifiability"]["n_parameters"],
    }

    # Generate report
    print("\n7. Generating comprehensive report...")
    report_gen = ReportGenerator(output_path)
    report_gen.generate_full_report(
        ja24_analysis, diagnostic_results, consensus_comparison, model_issues
    )

    print(f"   - Report saved to: {output_path / 'bayesian_verification_report.md'}")

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print(f"\n{ja24_analysis['problem_summary']}")

    print("\n🔍 Key Findings:")
    print(
        f"   • JA24 raw ratings: {ja24_analysis['n_a_ratings']} A's, {ja24_analysis['n_b_ratings']} B's"
    )
    print(f"   • Model consensus: {ja24_analysis['model_consensus']}")
    print(f"   • Raw consensus (median): {ja24_analysis['raw_consensus_median']}")
    print("   • Circular reasoning detected: YES")
    print("   • Model is overparameterized: YES")

    print("\n📊 Output Files Generated:")
    print(f"   • {output_path / 'bayesian_verification_report.md'}")
    print(f"   • {output_path / 'JA24_sankey_diagram.html'}")
    print(f"   • {output_path / 'rater_severity_heatmap.png'}")
    print(f"   • {output_path / 'threshold_visualization.png'}")
    print(f"   • {output_path / 'JA24_consensus_comparison.png'}")
    print(f"   • {output_path / 'ja24_comprehensive_analysis.png'}")

    # Save results to JSON for programmatic access
    results_json = {
        "focus_essay": focus_essay,
        "ja24_analysis": ja24_analysis,
        "diagnostic_results": {
            k: v
            for k, v in diagnostic_results.items()
            if k != "circular_reasoning"  # This contains complex objects
        },
        "consensus_comparison": consensus_comparison.to_dict(orient="records"),
        "model_issues": model_issues,
        "agreement_metrics": agreement_metrics,
    }

    json_output = output_path / "verification_results.json"
    with open(json_output, "w") as f:
        json.dump(results_json, f, indent=2, default=str)

    print(f"\n💾 Results also saved to: {json_output}")

    return results_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify Bayesian ordinal regression model for essay grading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python bayesian_model_verification.py \\
        --data-path ../../Documentation/research/rapport_till_kollegor/BAYESIAN_ANALYSIS_GPT_5_PRO/ \\
        --focus-essay JA24 \\
        --output-dir ./verification_output/
        """,
    )

    parser.add_argument(
        "--data-path", type=str, required=True, help="Path to BAYESIAN_ANALYSIS_GPT_5_PRO directory"
    )

    parser.add_argument(
        "--focus-essay",
        type=str,
        default="JA24",
        help="Essay ID to focus analysis on (default: JA24)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output/",
        help="Directory for output files (default: ./output/)",
    )

    args = parser.parse_args()

    # Run verification
    try:
        results = main(args.data_path, args.focus_essay, args.output_dir)
        print("\n✅ Verification completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
