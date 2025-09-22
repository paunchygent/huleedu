"""Debug script to analyze the temperature scaling approach in the Bayesian consensus model."""

import numpy as np
import pandas as pd
from improved_bayesian_model import ImprovedBayesianModel, ModelConfig


def simulate_confidence_with_temperature(ability, thresholds, temperatures):
    """Simulate confidence calculation with different temperature values."""
    n_categories = 6  # Swedish grades F-A
    results = []

    for temp in temperatures:
        probs = np.zeros(n_categories)
        extended_thresholds = np.concatenate([[-np.inf], thresholds, [np.inf]])

        for i in range(n_categories):
            lower = extended_thresholds[i]
            upper = extended_thresholds[i + 1]

            # Use logistic CDF with temperature scaling
            p_upper = 1 / (1 + np.exp(-((ability - upper) / temp)))
            p_lower = 1 / (1 + np.exp(-((ability - lower) / temp)))
            probs[i] = p_upper - p_lower

        # Normalize
        probs = probs / probs.sum()

        # Get max confidence
        max_conf = np.max(probs)
        max_grade = np.argmax(probs)

        results.append(
            {
                "temperature": temp,
                "max_confidence": max_conf,
                "grade": max_grade,
                "probabilities": probs,
            }
        )

    return results


def test_consensus_scenarios():
    """Test different consensus scenarios."""

    print("=" * 80)
    print("ANALYZING TEMPERATURE SCALING IN BAYESIAN CONSENSUS MODEL")
    print("=" * 80)

    # Create test data for strong consensus case (e.g., 4/5 raters agree)
    strong_consensus_data = pd.DataFrame(
        [
            {"essay_id": "TEST1", "rater_id": "R1", "grade": "B"},
            {"essay_id": "TEST1", "rater_id": "R2", "grade": "B"},
            {"essay_id": "TEST1", "rater_id": "R3", "grade": "B"},
            {"essay_id": "TEST1", "rater_id": "R4", "grade": "B"},
            {"essay_id": "TEST1", "rater_id": "R5", "grade": "C"},
        ]
    )

    # Test with different temperature values
    temperatures = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]

    print("\n1. TESTING WITH DIFFERENT TEMPERATURE VALUES")
    print("-" * 50)

    for temp in temperatures:
        # Modify model config to use this temperature
        config = ModelConfig(n_chains=2, n_draws=1000, n_tune=500)
        model = ImprovedBayesianModel(config)

        # We need to patch the temperature value in _calculate_grade_probabilities
        # For now, let's simulate the effect

        # Typical thresholds (from Swedish grade distribution)
        thresholds = np.array([-2.197, -0.368, 0.223, 0.882, 1.365])

        # Simulate an ability score that should map to B (around 1.1)
        ability = 1.1

        results = simulate_confidence_with_temperature(ability, thresholds, [temp])
        result = results[0]

        grades = ["F", "E", "D", "C", "B", "A"]
        grade = grades[result["grade"]]

        print(
            f"Temperature: {temp:4.1f} -> Grade: {grade}, Confidence: {result['max_confidence']:.3f}"
        )

    print("\n2. ANALYZING THE MATHEMATICAL APPROACH")
    print("-" * 50)
    print("Temperature scaling affects the steepness of the logistic function:")
    print("- T < 1.0: Sharper transitions (higher confidence)")
    print("- T = 1.0: Standard logistic function")
    print("- T > 1.0: Smoother transitions (lower confidence)")

    print("\n3. PROBLEMS WITH TEMPERATURE SCALING:")
    print("-" * 50)
    print("a) It's a post-hoc adjustment, not based on actual uncertainty")
    print("b) Doesn't reflect the true posterior distribution")
    print("c) Can give artificially high confidence for borderline cases")
    print("d) Ignores the variance in the posterior samples")

    print("\n4. BETTER ALTERNATIVES:")
    print("-" * 50)
    print("a) Use the posterior variance directly from MCMC samples")
    print("b) Calculate confidence intervals from the posterior distribution")
    print("c) Use entropy of the grade distribution as uncertainty measure")
    print("d) Model rater agreement explicitly as a hierarchical component")

    # Now test the actual model
    print("\n5. TESTING ACTUAL MODEL WITH STRONG CONSENSUS")
    print("-" * 50)

    config = ModelConfig(n_chains=2, n_draws=1000, n_tune=500)
    model = ImprovedBayesianModel(config)
    model.fit(strong_consensus_data)

    results = model.get_consensus_grades()
    test_result = results["TEST1"]

    print(f"Consensus Grade: {test_result.consensus_grade}")
    print(f"Confidence: {test_result.confidence:.3f}")
    print("Grade Probabilities:")
    for grade, prob in test_result.grade_probabilities.items():
        print(f"  {grade}: {prob:.3f}")

    print("\n6. ANALYZING POSTERIOR UNCERTAINTY")
    print("-" * 50)

    # Extract posterior samples for ability
    essay_abilities = model.trace.posterior["essay_ability"].values
    ability_samples = essay_abilities[0, :, 0]  # First chain, all draws, first essay

    print(f"Ability mean: {np.mean(ability_samples):.3f}")
    print(f"Ability std: {np.std(ability_samples):.3f}")
    print(
        f"95% CI: [{np.percentile(ability_samples, 2.5):.3f}, {np.percentile(ability_samples, 97.5):.3f}]"
    )

    # Calculate how often each grade would be selected across samples
    grade_counts = np.zeros(6)
    thresholds = (
        model.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values
        if "thresholds" in model.trace.posterior
        else model._get_swedish_informed_thresholds()
    )

    for ability in ability_samples:
        probs = model._calculate_grade_probabilities(ability, thresholds)
        grade_counts[np.argmax(probs)] += 1

    grade_frequencies = grade_counts / len(ability_samples)

    print("\nGrade selection frequency across posterior samples:")
    for i, grade in enumerate(["F", "E", "D", "C", "B", "A"]):
        print(f"  {grade}: {grade_frequencies[i]:.3f}")

    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("Temperature scaling is a hack. Better approach would be to:")
    print("1. Use the posterior distribution variance directly")
    print("2. Calculate confidence from grade selection frequency across samples")
    print("3. Model rater consensus explicitly in the hierarchical structure")
    print("=" * 80)


if __name__ == "__main__":
    test_consensus_scenarios()
