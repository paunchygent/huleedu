"""Debug script to understand the JA24 issue in detail."""

from __future__ import annotations

import numpy as np
import pandas as pd
from improved_bayesian_model import ImprovedBayesianModel, ModelConfig

def analyze_ja24_issue():
    """Analyze the JA24 problem step by step."""

    # JA24 case: 5 As, 2 Bs
    ratings = pd.DataFrame([
        {'essay_id': 'JA24', 'rater_id': 'R1', 'grade': 'A'},
        {'essay_id': 'JA24', 'rater_id': 'R2', 'grade': 'A'},
        {'essay_id': 'JA24', 'rater_id': 'R3', 'grade': 'A'},
        {'essay_id': 'JA24', 'rater_id': 'R4', 'grade': 'A'},
        {'essay_id': 'JA24', 'rater_id': 'R5', 'grade': 'A'},
        {'essay_id': 'JA24', 'rater_id': 'R6', 'grade': 'B'},
        {'essay_id': 'JA24', 'rater_id': 'R7', 'grade': 'B'},
    ])

    print("=" * 80)
    print("JA24 ISSUE ANALYSIS")
    print("=" * 80)
    print("\n1. INPUT DATA:")
    print(f"   - 5 raters gave 'A' (71.4%)")
    print(f"   - 2 raters gave 'B' (28.6%)")
    print(f"   - Expected consensus: A")

    # Test with different configurations
    configs = [
        ("Default", ModelConfig()),
        ("No empirical thresholds", ModelConfig(use_empirical_thresholds=False)),
        ("Higher sparse threshold", ModelConfig(sparse_data_threshold=5)),
        ("Force complex model", ModelConfig(sparse_data_threshold=100)),
    ]

    for config_name, config in configs:
        print(f"\n2. TESTING WITH: {config_name}")
        print("-" * 40)

        model = ImprovedBayesianModel(config)
        data_df = model.prepare_data(ratings)

        # Show data stats
        print(f"   Observations: {len(data_df)}")
        grades_numeric = data_df['grade_numeric'].values
        print(f"   Numeric grades: {grades_numeric}")
        print(f"   Mean numeric: {np.mean(grades_numeric):.2f}")

        # Show thresholds
        thresholds = model._get_empirical_thresholds(grades_numeric)
        print(f"   Empirical thresholds: {thresholds}")

        # Check model selection
        use_simple = len(data_df) < config.sparse_data_threshold
        print(f"   Model type: {'Simple' if use_simple else 'Complex'}")

        # Build and analyze model structure
        pm_model = model.build_model(data_df)

        # Count parameters
        if use_simple:
            n_params = 1 + 1  # 1 essay ability + 1 global severity
            print(f"   Parameters: {n_params} (1 ability + 1 global severity)")
        else:
            n_params = 1 + 7  # 1 essay ability + 7 rater severities
            print(f"   Parameters: {n_params} (1 ability + 7 rater severities)")

        print(f"   Observations/Parameters ratio: {len(data_df)/n_params:.1f}")

        # Fit the model
        print(f"\n   Fitting model...")
        model.fit(ratings)

        # Get results
        results = model.get_consensus_grades()
        ja24_result = results['JA24']

        print(f"\n   RESULTS:")
        print(f"   Consensus grade: {ja24_result.consensus_grade}")
        print(f"   Confidence: {ja24_result.confidence:.2%}")
        print(f"   Raw ability: {ja24_result.raw_ability:.3f}")

        print(f"\n   Grade probabilities:")
        for grade in ['F', 'E', 'D', 'C', 'B', 'A']:
            prob = ja24_result.grade_probabilities[grade]
            bar = '█' * int(prob * 20)
            print(f"   {grade}: {prob:6.2%} {bar}")

        # Analyze thresholds vs ability
        if model.trace is not None:
            ability_mean = model.trace.posterior["essay_ability"].mean().values[0]

            if "thresholds" in model.trace.posterior:
                thresh_mean = model.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values
            else:
                # Fixed thresholds case
                thresh_mean = thresholds

            print(f"\n   Threshold analysis:")
            print(f"   Ability: {ability_mean:.3f}")
            extended = np.concatenate([[-np.inf], thresh_mean, [np.inf]])
            for i, grade in enumerate(['F', 'E', 'D', 'C', 'B', 'A']):
                in_range = extended[i] < ability_mean <= extended[i+1]
                marker = " <-- HERE" if in_range else ""
                print(f"   {grade}: ({extended[i]:.3f}, {extended[i+1]:.3f}]{marker}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    analyze_ja24_issue()