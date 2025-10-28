# ✅ Ordinal Kernel Consensus Model

The consensus grader now uses a lightweight kernel smoother on top of raw grade
counts. Each rating contributes most weight to its own grade and a decaying
amount to neighbouring grades, and we down-weight raters with low coverage or
poor alignment. By default the consensus grade is the rounded expected grade index, with an optional argmax decision rule;
confidence is the smoothed probability mass at the selected grade, and the full
probability vector is exposed for inspection.

## Quick Start

```bash
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/new_validated \
    --verbose
```

Outputs:

- `essay_consensus.csv`
- `essay_grade_probabilities.csv`
- `model_diagnostics.json`
- `rater_weights.csv`
- `rater_severity.csv`
- `rater_agreement.csv`
- `rater_spread.csv`
- `essay_inter_rater_stats.csv`

> ⚠️ **Rater weights are deliberate but not final.** You should experiment with
> `RaterSeverityConfig` in upcoming sessions and benchmark alternative severity
> schemes to see which delivers the most robust consensus grades. A follow-up
> evaluator module will compare probability quality across methods. We also want
> to explore weighting severity by the **confidence in each rater’s observed bias**—
> high-confidence bias should carry more predictive influence while low-confidence
> bias should be penalised.

## Behaviour

- Grades with split votes (e.g., EK24: B, B, C-, D+) now yield consensus at the
  rounded mean (C+) with moderate probability mass spread across adjacent
  categories.
- Mixed low/high cases (JP24) surface low confidence because the smoothed
  distribution remains broad.
- Clean majorities (JA24 → A) retain high confidence because the kernel leaves
  most mass on the rated grade while still reflecting rater reliability.

## Feature Toggles

Set these fields on `KernelConfig` (or CLI equivalents) to evaluate improvements individually:

| Feature | What | Why |
| --- | --- | --- |
| `use_argmax_decision` | Emit the highest-probability grade instead of rounding the expected index. | Keeps the published grade aligned with the modal posterior mass when distributions are skewed or bimodal. |
| `use_loo_alignment` | Recompute essay means with the focal rater removed before weighting and bias estimation. | Prevents a rater from anchoring their own deviation when panels are tiny, stabilising bias shrinkage. |
| `use_precision_weights` | Scale reliability weights by posterior precision and bias magnitude. | Prioritises raters whose behaviour we understand well while attenuating noisy outliers. |
| `use_neutral_gating` | Compute neutral ESS per essay (informational only). | Highlights balanced evidence while leaving release decisions to coordinators. |

See `scripts/bayesian_consensus_model/evaluation/harness.py` for automated ablation studies and comparative reports.

## Tests

```bash
pdm run pytest scripts/bayesian_consensus_model/tests/test_model_core.py -q
```

The suite covers data prep, fitting, and consensus extraction on small panels.

## Notes

- No latent-threshold estimation or MCMC is used; rater severity comes from
  simple volume/alignment heuristics.
- Configuration now includes feature flags for argmax decision, leave-one-out alignment, precision-aware weighting, and neutral ESS metrics (see above).
