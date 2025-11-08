"""
Example usage of the Ordinal Essay Scoring Module
==================================================
Demonstrates integration with async microservices and Swedish essay data.
"""

import asyncio
from datetime import datetime
from typing import List

from ordinal_essay_scoring import (
    GradeScale,
    ManyFacetRaschModel,
    OrdinalScoringService,
    RatingData,
    design_optimal_rating_schedule,
)

# =============================================================================
# Swedish Essay Data from your CSV
# =============================================================================


def load_swedish_essay_data() -> List[RatingData]:
    """Load the Swedish national exam essay data."""

    # Your actual data
    raw_data = [
        (
            "TK24",
            [
                ("Lena R", "C+"),
                ("Yvonne R", "C-"),
                ("Agneta D", "D+"),
                ("Anna P", "D+"),
                ("Jenny L", "C-"),
            ],
        ),
        (
            "HJ17",
            [
                ("Lena R", "C-"),
                ("Sophie O", "D+"),
                ("Yvonne R", "D+"),
                ("Jenny L", "C+"),
                ("Jenny P", "D"),
            ],
        ),
        ("SA24", [("Lena R", "D+"), ("Sophie O", "D+"), ("Agneta D", "D+"), ("Robin S", "D-")]),
        ("JP24", [("Ann B", "C-"), ("Ullis", "C-"), ("Sophie O", "E"), ("Anna P", "F+")]),
        (
            "JF24",
            [
                ("Ann B", "D+"),
                ("Ullis", "D+"),
                ("Erik A", "C-"),
                ("Anna P", "D+"),
                ("Robin S", "E+"),
            ],
        ),
        ("SN24", [("Ann B", "C-"), ("Jenny L", "D-"), ("Mats A", "D+"), ("Robin S", "C-")]),
        ("EK24", [("Ullis", "B"), ("Erik A", "B"), ("Marcus D", "C-"), ("Robin S", "D+")]),
        (
            "LW24",
            [
                ("Erik A", "D+"),
                ("Marcus D", "E-"),
                ("Sophie O", "C-"),
                ("Agneta D", "C-"),
                ("Anna P", "C-"),
                ("Jenny L", "E+"),
                ("Jenny P", "E+"),
                ("Robin S", "D-"),
            ],
        ),
        (
            "JA24",
            [
                ("Erik A", "A"),
                ("Yvonne R", "B"),
                ("Agneta D", "B"),
                ("Anna P", "A"),
                ("Jenny L", "A"),
                ("Jenny P", "A"),
            ],
        ),
        ("ER24", [("Erik A", "C+"), ("Yvonne R", "C-"), ("Anna P", "C-"), ("Jenny L", "C-")]),
        (
            "ES24",
            [
                ("Erik A", "C+"),
                ("Anna P", "B"),
                ("Jenny L", "C-"),
                ("Jenny P", "A"),
                ("Mats A", "C+"),
                ("Robin S", "C+"),
            ],
        ),
        (
            "II24",
            [
                ("Yvonne R", "B"),
                ("Anna P", "B"),
                ("Jenny L", "B"),
                ("Jenny P", "C+"),
                ("Mats A", "C+"),
            ],
        ),
    ]

    # Convert to RatingData objects
    grade_map = {
        "F": GradeScale.F,
        "F+": GradeScale.F_PLUS,
        "E-": GradeScale.E_MINUS,
        "E": GradeScale.E,
        "E+": GradeScale.E_PLUS,
        "D-": GradeScale.D_MINUS,
        "D": GradeScale.D,
        "D+": GradeScale.D_PLUS,
        "C-": GradeScale.C_MINUS,
        "C": GradeScale.C,
        "C+": GradeScale.C_PLUS,
        "B-": GradeScale.B_MINUS,
        "B": GradeScale.B,
        "B+": GradeScale.B_PLUS,
        "A": GradeScale.A,
    }

    ratings = []
    for essay_id, rater_grades in raw_data:
        for rater_id, grade_str in rater_grades:
            if grade_str in grade_map:
                ratings.append(
                    RatingData(
                        essay_id=essay_id,
                        rater_id=rater_id,
                        grade=grade_map[grade_str],
                        timestamp=datetime.now().timestamp(),
                    )
                )

    return ratings


# =============================================================================
# Direct MFRM Analysis
# =============================================================================


def run_direct_analysis():
    """Run MFRM analysis directly (synchronous)."""

    print("=" * 60)
    print("MFRM ANALYSIS - Swedish Essay Scoring")
    print("=" * 60)

    # Load data
    ratings = load_swedish_essay_data()
    print(f"\nLoaded {len(ratings)} ratings")

    # Create model
    model = ManyFacetRaschModel(
        n_categories=15,  # F to A (15 levels in Swedish scale)
        robust_errors=True,
        student_t_nu=None,  # Estimate nu
        use_hierarchical=True,
    )

    # Check connectivity before fitting
    df = model.prepare_data(ratings)
    connectivity = model.check_connectivity(df)

    print("\n📊 Data Connectivity:")
    print(f"  - Connected: {connectivity['is_connected']}")
    print(f"  - Components: {connectivity['n_components']}")
    print(f"  - Sparsity: {connectivity['sparsity']:.1%}")
    print(f"  - Min raters/essay: {connectivity['min_raters_per_essay']}")
    print(f"  - Min essays/rater: {connectivity['min_essays_per_rater']}")

    # Fit model
    print("\n🔧 Fitting MFRM model (this takes 2-3 minutes)...")
    results = model.fit(ratings, draws=2000, chains=4, tune=1000, target_accept=0.9)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print("\n📝 Essay Scores (sorted by ability):")
    print("-" * 40)
    sorted_essays = sorted(results.essay_scores, key=lambda x: x.latent_ability.mean, reverse=True)

    for essay in sorted_essays:
        print(
            f"{essay.essay_id:8} | "
            f"Ability: {essay.latent_ability.mean:6.3f} ± {essay.latent_ability.std:5.3f} | "
            f"Grade: {essay.predicted_grade.name:8} | "
            f"Uncertainty: {essay.uncertainty_score:.1%}"
        )

    print("\n👥 Rater Effects (severity: + = strict, - = lenient):")
    print("-" * 40)
    sorted_raters = sorted(results.rater_effects, key=lambda x: x.severity.mean)

    for rater in sorted_raters:
        severity_bar = "█" * int(abs(rater.severity.mean * 10))
        direction = "→" if rater.severity.mean > 0 else "←"
        print(
            f"{rater.rater_id:12} | "
            f"{rater.severity.mean:+6.3f} ± {rater.severity.std:5.3f} | "
            f"{direction} {severity_bar} ({rater.interpretation})"
        )

    print("\n📊 Threshold Estimates:")
    print("-" * 40)
    grade_transitions = [
        "F→F+",
        "F+→E-",
        "E-→E",
        "E→E+",
        "E+→D-",
        "D-→D",
        "D→D+",
        "D+→C-",
        "C-→C",
        "C→C+",
        "C+→B-",
        "B-→B",
        "B→B+",
        "B+→A",
    ]

    for i, (threshold, transition) in enumerate(
        zip(results.threshold_estimates, grade_transitions)
    ):
        print(
            f"Threshold {i + 1:2d} ({transition:8}): "
            f"{threshold.mean:6.3f} [{threshold.hdi_lower:6.3f}, {threshold.hdi_upper:6.3f}]"
        )

    print("\n🔍 Agreement Metrics:")
    print("-" * 40)
    for metric, value in results.agreement_metrics.items():
        print(f"{metric:30}: {value:.3f}")

    print("\n✅ Model Diagnostics:")
    print("-" * 40)
    diag = results.diagnostics
    print(f"Max R-hat: {diag.max_rhat:.4f} (should be < 1.01)")
    print(f"Min ESS bulk: {diag.min_ess_bulk:.0f}")
    print(f"Min ESS tail: {diag.min_ess_tail:.0f}")
    print(f"Divergences: {diag.divergences}")
    print(f"Energy BFMI: {diag.energy_bfmi:.3f}")

    if diag.loo_elpd:
        print(f"LOO-ELPD: {diag.loo_elpd:.1f}")
    if diag.waic:
        print(f"WAIC: {diag.waic:.1f}")

    # Check convergence
    if diag.max_rhat < 1.01 and diag.divergences == 0:
        print("\n✅ Model converged successfully!")
    else:
        print("\n⚠️ Potential convergence issues - consider increasing samples")

    return results


# =============================================================================
# Async Service Integration (for microservices)
# =============================================================================


async def run_async_service():
    """
    Example of async service integration for microservices.
    This would be called from your Quart/FastAPI endpoints.
    """

    print("\n" + "=" * 60)
    print("ASYNC SERVICE INTEGRATION")
    print("=" * 60)

    # Initialize service
    service = OrdinalScoringService()

    # Load data
    ratings = load_swedish_essay_data()

    # Fit model asynchronously
    print("\n🔧 Fitting model asynchronously...")
    results = await service.fit_model(
        ratings,
        draws=1000,  # Fewer draws for faster demo
        chains=4,
        tune=500,
    )

    print("\n✅ Model fitted successfully")
    print(f"   - {len(results.essay_scores)} essays scored")
    print(f"   - {len(results.rater_effects)} raters calibrated")

    # Example: Score a specific essay
    essay_id = "JA24"
    essay_scores = [s for s in results.essay_scores if s.essay_id == essay_id]

    if essay_scores:
        score = essay_scores[0]
        print(f"\n📝 Essay {essay_id} Score:")
        print(f"   - Predicted Grade: {score.predicted_grade.name}")
        print(f"   - Latent Ability: {score.latent_ability.mean:.3f}")
        print(
            f"   - 95% HDI: [{score.latent_ability.hdi_lower:.3f}, "
            f"{score.latent_ability.hdi_upper:.3f}]"
        )
        print("   - Grade Probabilities:")
        for grade, prob in sorted(
            score.grade_probabilities.items(), key=lambda x: x[1], reverse=True
        )[:5]:
            if prob > 0.01:
                print(f"      {grade.name:8}: {prob:6.1%}")

    # Example: Get rater bias
    rater_id = "Anna P"
    rater_effect = await service.get_rater_bias(rater_id)

    if rater_effect:
        print(f"\n👤 Rater {rater_id} Effect:")
        print(f"   - Severity: {rater_effect.severity.mean:+.3f}")
        print(f"   - Interpretation: {rater_effect.interpretation}")
        print(f"   - Consistency: {rater_effect.consistency:.3f}")

    # Cross-validation
    print("\n🔄 Running cross-validation...")
    cv_results = await service.cross_validate(ratings, n_folds=3)

    print("\nCross-validation metrics:")
    for metric, values in cv_results.items():
        if values:
            print(f"   {metric}: {np.mean(values):.3f} ± {np.std(values):.3f}")

    return service


# =============================================================================
# API Endpoint Examples (for Quart/FastAPI)
# =============================================================================

"""
Example Quart/FastAPI endpoints:

from quart import Quart, jsonify, request
from ordinal_essay_scoring import OrdinalScoringService, RatingData

app = Quart(__name__)
scoring_service = OrdinalScoringService()

@app.route('/api/v1/fit', methods=['POST'])
async def fit_model():
    '''Fit MFRM model to rating data.'''
    data = await request.get_json()

    # Convert JSON to RatingData objects
    ratings = [RatingData(**r) for r in data['ratings']]

    # Fit model
    results = await scoring_service.fit_model(ratings)

    return jsonify({
        'success': True,
        'n_essays': len(results.essay_scores),
        'n_raters': len(results.rater_effects),
        'diagnostics': results.diagnostics.dict()
    })

@app.route('/api/v1/score/<essay_id>')
async def get_essay_score(essay_id: str):
    '''Get score for specific essay.'''
    score = await scoring_service.score_essay(essay_id, [], use_cached_model=True)

    return jsonify({
        'essay_id': essay_id,
        'predicted_grade': score.predicted_grade.name,
        'ability': score.latent_ability.dict(),
        'uncertainty': score.uncertainty_score
    })

@app.route('/api/v1/rater/<rater_id>')
async def get_rater_effect(rater_id: str):
    '''Get rater bias estimate.'''
    effect = await scoring_service.get_rater_bias(rater_id)

    if effect:
        return jsonify(effect.dict())
    else:
        return jsonify({'error': 'Rater not found'}), 404
"""


# =============================================================================
# Rating Schedule Design
# =============================================================================


def demonstrate_rating_design():
    """Demonstrate optimal rating schedule design."""

    print("\n" + "=" * 60)
    print("OPTIMAL RATING SCHEDULE DESIGN")
    print("=" * 60)

    # Design parameters
    n_essays = 50
    n_raters = 10
    essays_per_rater = 15

    print("\nDesigning schedule for:")
    print(f"  - {n_essays} essays")
    print(f"  - {n_raters} raters")
    print(f"  - {essays_per_rater} essays per rater")

    # Generate schedule
    schedule = design_optimal_rating_schedule(
        n_essays=n_essays,
        n_raters=n_raters,
        essays_per_rater=essays_per_rater,
        ensure_connectivity=True,
        min_overlap=2,
    )

    print(f"\nGenerated {len(schedule)} assignments")

    # Analyze schedule
    from collections import defaultdict

    essays_per_rater_actual = defaultdict(int)
    raters_per_essay = defaultdict(int)

    for essay, rater in schedule:
        essays_per_rater_actual[rater] += 1
        raters_per_essay[essay] += 1

    print("\nSchedule statistics:")
    print(f"  - Min raters per essay: {min(raters_per_essay.values())}")
    print(f"  - Max raters per essay: {max(raters_per_essay.values())}")
    print(f"  - Avg raters per essay: {np.mean(list(raters_per_essay.values())):.1f}")
    print(f"  - Min essays per rater: {min(essays_per_rater_actual.values())}")
    print(f"  - Max essays per rater: {max(essays_per_rater_actual.values())}")

    return schedule


# =============================================================================
# Main Execution
# =============================================================================


def main():
    """Run all examples."""

    print("\n" + "🎯" * 30)
    print("ORDINAL ESSAY SCORING WITH RATER BIAS ADJUSTMENT")
    print("Swedish National Exam Implementation")
    print("🎯" * 30)

    # 1. Direct MFRM analysis
    print("\n1️⃣ RUNNING DIRECT MFRM ANALYSIS")
    results = run_direct_analysis()

    # 2. Async service (for microservices)
    print("\n2️⃣ RUNNING ASYNC SERVICE INTEGRATION")
    asyncio.run(run_async_service())

    # 3. Rating schedule design
    print("\n3️⃣ DEMONSTRATING OPTIMAL RATING DESIGN")
    demonstrate_rating_design()

    print("\n" + "=" * 60)
    print("✅ ALL EXAMPLES COMPLETED")
    print("=" * 60)

    return results


if __name__ == "__main__":
    # For testing, you might want to use fewer MCMC samples
    import numpy as np

    # Set random seed for reproducibility
    np.random.seed(42)

    # Run examples
    results = main()

    print("\n💾 Results available in 'results' variable")
