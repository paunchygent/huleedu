# Handoff – Ordinal Kernel Consensus Model

## Summary

The consensus grader now computes rounded expected grade indices from raw vote
counts, then applies a Gaussian kernel (σ configurable) to obtain smooth
probability distributions. Raters are scaled by reliability weights derived from
volume and agreement, so sparse or erratic raters carry less influence.

Pipeline per essay:

1. Map grades to indices and gather rater weights.
2. Calculate the weighted expected grade index `E[k]` and round to choose the
   headline grade.
3. For uncertainty, add each rating’s weight to a Gaussian kernel centred on its
   grade and normalise to produce probability mass over all categories.
4. Confidence is the smoothed probability at the consensus grade. Full
   probabilities and inter-rater summaries are emitted alongside the consensus.

## Usage

```
pdm run python -m scripts.bayesian_consensus_model.generate_reports \
    --ratings-csv scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv \
    --output-dir output/new_validated \
    --verbose
```

## Outputs

- `essay_consensus.csv`
- `essay_grade_probabilities.csv`
- `rater_weights.csv`
- `rater_severity.csv`
- `rater_agreement.csv`
- `rater_spread.csv`
- `essay_inter_rater_stats.csv`
- `model_diagnostics.json` (σ and pseudo-count used)

> ⚠️ **Rater severity weights remain a tuning lever.** Plan to compare this
> lightweight scheme against more robust severity estimators in the next
> session. The future evaluator module should run statistical certainty checks
> across competing methods rather than rely on hard thresholds. We also aim to
> tie severity to the **confidence in each rater’s estimated bias** so that highly
> certain bias adjustments have more predictive power while uncertain ones are
> penalised.

## Rater Metrics

`compute_rater_weights` (see `models/rater_severity.py`) produces:

- `weight` – normalised reliability weight.
- `n_rated` – number of essays graded.
- `rms_alignment` / `mad_alignment` – disagreement with essay means.
- `grade_range`, `unique_grades`, `std_grade_index` – spread diagnostics.

These feed directly into the kernel smoother and are written to CSV for audit.

## Behaviour on Anchors

| Essay | Consensus | Confidence | Notes |
|-------|-----------|------------|-------|
| EK24  | C+        | 0.18       | Weighted mean of B/B/C-/D+, mass across C+/B |
| ES24  | C+        | 0.31       | Broad support including B/A tail |
| JP24  | E+        | 0.08       | Split panel yields low confidence |
| LW24  | D+        | 0.20       | Wide disagreement, consensus near centre |

## Next Steps

- If deeper severity modelling is required, replace the heuristic weights with a
  proper many-facet Rasch calibration and reuse the kernel consensus.
- Tune σ or pseudo-count per essay type as additional anchor data arrives.
- Extend outputs with pairwise agreement heatmaps if needed.
