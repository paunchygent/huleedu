#!/usr/bin/env python3
"""Debug script to understand why ES24 is getting wrong consensus grade."""

import pandas as pd
import numpy as np
from bayesian_consensus_model import ImprovedBayesianModel, ModelConfig

def main():
    # Load data
    df = pd.read_csv(
        'anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv',
        sep=';', skiprows=1
    )

    # Convert to long format
    essay_col, file_col = df.columns[:2]
    rater_cols = df.columns[2:]

    long_df = df.melt(
        id_vars=[essay_col, file_col],
        value_vars=rater_cols,
        var_name='rater_id',
        value_name='grade'
    ).rename(columns={essay_col: 'essay_id', file_col: 'file_name'})

    long_df['grade'] = long_df['grade'].astype(str).str.strip().str.upper().replace({'': np.nan, 'NAN': np.nan})
    long_df = long_df.dropna(subset=['grade'])
    ratings_df = long_df[['essay_id', 'rater_id', 'grade']]

    # Show all essay ratings summary
    print("=== ESSAY RATINGS SUMMARY ===")
    for essay_id in ratings_df['essay_id'].unique():
        essay_grades = ratings_df[ratings_df['essay_id'] == essay_id]['grade'].tolist()
        grade_counts = pd.Series(essay_grades).value_counts()
        print(f"\n{essay_id}: {', '.join(essay_grades)}")
        print(f"  Most common: {grade_counts.index[0]} ({grade_counts.iloc[0]} votes)")

    # Focus on problematic essays
    print("\n\n=== PROBLEMATIC ESSAYS ===")

    # ES24: Should be C+ but getting C-
    es24_grades = ratings_df[ratings_df['essay_id'] == 'ES24']['grade'].tolist()
    print(f"\nES24 actual grades: {es24_grades}")
    print(f"  Should be: C+ (3/6 votes)")
    print(f"  Model gives: C-")

    # Check if there are rater effects
    print("\n=== RATER ANALYSIS FOR ES24 ===")
    es24_data = ratings_df[ratings_df['essay_id'] == 'ES24']
    for _, row in es24_data.iterrows():
        # Count how many essays this rater rated
        rater_count = len(ratings_df[ratings_df['rater_id'] == row['rater_id']])
        # Get average grade this rater gives
        rater_grades = ratings_df[ratings_df['rater_id'] == row['rater_id']]['grade'].tolist()
        print(f"  {row['rater_id']}: gave {row['grade']} (rates {rater_count} essays)")

    # Fit a simple model to check
    print("\n=== FITTING MODEL ===")
    # Try with different thresholds
    config = ModelConfig(
        n_chains=2,
        n_draws=1000,
        n_tune=1000,
        sparse_data_threshold=7,  # Increase threshold so ES24 uses majority voting
        majority_override_ratio=0.5  # Lower threshold to trigger override
    )

    model = ImprovedBayesianModel(config)
    model.fit(ratings_df)

    results = model.get_consensus_grades()

    # Check ES24
    if 'ES24' in results:
        es24_result = results['ES24']
        print(f"\nES24 Model Result:")
        print(f"  Consensus: {es24_result.consensus_grade}")
        print(f"  Confidence: {es24_result.confidence:.3f}")
        print(f"  Raw ability: {es24_result.raw_ability:.3f}")
        print(f"  Grade probabilities:")
        for grade, prob in es24_result.grade_probabilities.items():
            if prob > 0.01:
                print(f"    {grade}: {prob:.3f}")

    # Check if it's a majority override case
    es24_rating_count = len(es24_grades)
    print(f"\nES24 has {es24_rating_count} ratings")
    print(f"Sparse threshold: {config.sparse_data_threshold}")
    print(f"Is sparse? {es24_rating_count < config.sparse_data_threshold}")

    # Manual calculation of what it should be
    from collections import Counter
    es24_counter = Counter(es24_grades)
    most_common = es24_counter.most_common(1)[0]
    print(f"\nManual calculation:")
    print(f"  Most common grade: {most_common[0]} with {most_common[1]}/{len(es24_grades)} votes")
    print(f"  Majority ratio: {most_common[1]/len(es24_grades):.2f}")

if __name__ == "__main__":
    main()