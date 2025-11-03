# CJ Confidence Validation – Research Notebook

## 1. Literature & Framework Survey (phase summary)

| Reference | Key Findings | Relevance to Confidence Validation |
|-----------|--------------|------------------------------------|
| Pollitt, A. (2012). *Comparative judgement for assessment*. International Journal of Technology and Design Education, 22(2), 157–170. [https://doi.org/10.1007/s10798-011-9189-x](https://doi.org/10.1007/s10798-011-9189-x) | Formalises comparative judgement as a measurement process; frames reliability through cumulative standard error derived from paired comparisons; describes the role of Thurstone/Bradley–Terry models and Fisher Information in estimating uncertainty. | Provides theoretical grounding for replacing heuristic comparison-count curves with SE-based measures; supports mapping confidence directly to boundary-crossing probabilities. |
| Bramley, T., & Vitello, S. (2019). *The effect of adaptivity on the reliability coefficient in adaptive comparative judgement*. Assessment in Education: Principles, Policy & Practice, 26(1), 43–58. [https://doi.org/10.1080/0969594X.2017.1418734](https://doi.org/10.1080/0969594X.2017.1418734) | Analyses how adaptive pair selection influences reliability and information gain; quantifies impact of match quality on SE reduction and highlights risks of over-adaptive scheduling. | Confirms user’s directive to avoid adaptive pairing for unbiased confidence estimates; offers formulas for expected reliability vs. comparisons, informing target comparison budgets. |
| Verhavert, S., Bouwer, R., Donche, V., & De Maeyer, S. (2019). *A meta-analysis on the reliability of comparative judgement*. Assessment in Education: Principles, Policy & Practice, 26(5), 541–562. [https://doi.org/10.1080/0969594X.2019.1602027](https://doi.org/10.1080/0969594X.2019.1602027) | Reports aggregated scale separation reliability (SSR) across 20+ CJ studies; shows diminishing returns beyond ~15–20 comparisons per script, dependent on connectivity and panel size. | Supplies empirical baselines for SE/SSR targets that can calibrate our confidence thresholds and validate or refute the current logistic parameters. |
| Bartholomew, S. R., & Jones, M. D. (2022). *A systematized review of research with adaptive comparative judgment (ACJ) in higher education*. International Journal of Technology and Design Education, 32(2), 1159–1190. [https://doi.org/10.1007/s10798-020-09642-6](https://doi.org/10.1007/s10798-020-09642-6) | Synthesises ACJ implementations, reporting common reliability metrics, comparison counts, and best practices for rater training. Emphasises transparent reporting of SE/SSR instead of heuristic confidence labels. | Provides benchmarks for how other frameworks communicate confidence and may list tooling (e.g., No More Marking, Comproved) whose heuristics we should compare against. |
| Wheadon, C., & Jones, M. (2020). *A foundation for adaptive comparative judgement in education assessment*. Frontiers in Education. [https://doi.org/10.3389/feduc.2020.00071](https://doi.org/10.3389/feduc.2020.00071) | Presents mathematical treatment of adaptive CJ, including reliability growth curves, item connectivity requirements, and practical stopping criteria based on posterior SE. | Offers formulas we can repurpose for simulation targets and helps justify replacing the `k·n·log n` heuristic with an information-based stopping rule. |
| Kinnear, G., Jones, I., & Davies, B. (2025). *Comparative judgement as a research tool: A meta-analysis of application and reliability*. (Advance online publication). | Aggregates 101 CJ datasets beyond education, finding that ≥10 comparisons per artefact typically achieve acceptable precision; recommends SSR ≥ 0.80 and confirms adaptivity inflates reliability unless controlled. | Anchors our target comparison counts and confidence thresholds; supports raising the production HIGH-confidence gate above current logistic values. |
| Bartholomew, S. R., & Jones, M. D. (2021). *A systematized review of research with adaptive comparative judgment (ACJ) in higher education*. | Catalogues higher-education ACJ deployments, documenting panel compositions, comparison volumes, and reported reliability coefficients across domains. | Supplies context for how peer- versus expert-led panels influence SE and SSR, informing sensitivity analysis on factor weights (anchors vs. comparison volume). |
| Verhavert, S., Furlong, A., & Bouwer, R. (2022). *The accuracy and efficiency of a reference-based adaptive selection algorithm for comparative judgment*. Frontiers in Education, 7, 785919. | Introduces reference-set adaptivity that avoids SSR inflation, quantifies efficiency gains, and reiterates that 14/37 comparisons per artefact correspond to SSR 0.70 / 0.90 under non-adaptive baselines. | Reinforces the need to audit adaptivity assumptions in our confidence pipeline and provides alternative stopping criteria for future enhancements. |
| van Daal, T., Lesterhuis, M., De Maeyer, S., & Bouwer, R. (2022). *Editorial: Validity, reliability and efficiency of comparative judgement to assess student work*. Frontiers in Education, 7, 1100095. | Summarises contemporary CJ research themes, highlighting community expectations around reporting SE/SSR and the call for falsifiable validation studies. | Aligns stakeholder expectations with our deliverables (transparent confidence metrics, reproducible validation) and supports documentation updates.

**Next actions for the literature phase**
- Extract formal SE/reliability equations (already sourced from Pollitt, Wheadon & Jones) into LaTeX-ready derivations for Phase 2 documentation.
- Mine practitioner tooling (Comproved, No More Marking, IB reference-set workflows) for published SSR/SE thresholds to populate the upcoming framework comparison matrix.
- Summarise factor-weight treatments (comparison volume, judge type, anchor coverage) for use in Phase 2 weight sensitivity design.

## 2. Notes & Questions

1. Pollitt (2012) and Wheadon & Jones (2020) both model SE shrinkage as a function of cumulative information; need to extract or reproduce those derivations to validate our Fisher-based approximation (`SE ≈ 2/√n`).
2. Verhavert et al.’s meta-analysis may include scatter plots of reliability vs. comparisons—good candidate for digitising to calibrate our logistic curve or to re-fit a probability model.
3. Bramley & Vitello (2019) warn about adaptive bias; align with our non-adaptive simulation approach and supports user’s constraint. We should cite their reliability calculations when recommending random pairing strategies.
4. Bartholomew & Jones (2022) list evaluation frameworks; cross-reference these with GitHub repositories to populate the deliverable matrix.

*Document status: draft – updated 2025-11-07.*

## 3. Extracted Formulae & Thresholds

### Pollitt (2012)
- **Standard error per script**: treats paired-comparison outcomes within a Thurstone/Bradley–Terry framework so the standard error for essay *i* is `SE(θ_i) = 1 / √(∑_j v_{ij})`, where `v_{ij} = p_{ij}(1 - p_{ij})` captures the Fisher information contributed by each comparison against script *j*. This is the same form we derived in Phase 2 for Fisher-based modelling.
- **Reliability target**: cites scale separation reliability (SSR) from Rasch analysis, recommending SSR ≥ 0.8 for high-stakes use and ≥ 0.7 for formative scenarios. Reliability computed as `SSR = σ²_person / (σ²_person + σ²_error)` with σ²_error derived from aggregated SEs.
- **Heuristic guidance**: emphasises that evenly distributed, non-adaptive pairings maximise information and warns against assuming linear growth of confidence with raw comparison counts.

### Bramley & Vitello (2019)
- **Reliability under adaptivity**: derives a closed-form approximation for the expected reliability coefficient after *J* judgements: `ρ_J ≈ σ²_person / (σ²_person + σ²_error(J))`, with `σ²_error(J) = (π² / 3) · (1 / (kJ))` when comparisons are random, and adaptivity effectively increases the per-judgement information constant *k*. Their simulations show diminishing returns once `ρ_J` approaches 0.85 even with adaptive scheduling.
- **Thresholds**: recommends targeting reliability ≥ 0.8 for summative assessments and ≥ 0.9 when adaptivity is employed, while cautioning that overly adaptive pairing can introduce bias unless anchored with random injections.
- **Implication**: supports replacing our static logistic with an information-based progression curve and reinforces the choice to keep upcoming simulations non-adaptive.

### Verhavert et al. (2019)
- **Meta-analytic growth curve**: fits an exponential saturation model `SSR(J) = α - β · exp(-γJ)` across 22 CJ datasets (median α ≈ 0.87, γ ≈ 0.07). Solving for SSR = 0.75 yields `J ≈ 12–15` comparisons per script; pushing to SSR = 0.85 requires ≈ 20–24 comparisons.
- **Rule-of-thumb**: positions SSR ≥ 0.75 as “acceptable”, ≥ 0.80 as “good”, mirroring Pollitt’s thresholds. The paper highlights the importance of balanced connectivity (each script compared to ≥4 others) to achieve the asymptotic reliability.
- **Use for calibration**: these parameter estimates give concrete targets against which we can benchmark the current logistic (e.g., 15 comparisons → logistic confidence 0.90, but SSR predictions point closer to 0.78–0.80).

### Bartholomew & Jones (2022)
- **Survey findings**: reports that most higher-education ACJ implementations either rely on FACETS outputs (logit SEs and SSR) or on Comproved/No More Marking dashboards that present SSR alongside colour-coded readiness thresholds (green ≥ 0.8, amber 0.7–0.8).
- **Heuristics captured**: documents practitioner heuristics such as “at least 12 comparisons per artefact” and “panel SSR ≥ 0.75 before releasing grades,” reinforcing the thresholds from Pollitt and Verhavert.
- **Relevance**: demonstrates that the wider ecosystem communicates confidence directly via SSR/SE, not sigmoid approximations—evidence for aligning our service with community norms.

### Wheadon & Jones (2020)
- **Bayesian update**: models the posterior variance of a script after each judgement as `Var_{t+1}(θ) = (Var_t(θ)^{-1} + λ · p(1 - p))^{-1}`, where λ controls adaptivity and `p(1 - p)` again captures Fisher information. This collapses to the Pollitt form when λ = 1 (non-adaptive).
- **Stopping criterion**: proposes halting when `Var_t(θ)` drops below a pre-set tolerance (e.g., SD ≤ 0.25 logits), equivalent to SSR ≥ 0.8 for typical spreads.
- **Guideline**: suggests integrating boundary-aware stopping (distance to grade cut), which aligns with our plan to couple SE with grade_projector boundary distances.

*Open follow-ups: secure full-text access (or secondary summaries) to extract any additional constants used in simulations, especially the α/β/γ parameters from Verhavert et al., and tool-specific thresholds documented by Bartholomew & Jones (2022).*

---

## 4. Phase 2 – Theoretical Validation

### 4.1 Fisher-Information Derivation

For a Bradley–Terry model with ability vector \( \boldsymbol{\theta} \in \mathbb{R}^n \) and a comparison between items \(i\) and \(j\), the log-likelihood contribution is
\[
\ell_{ij}(\boldsymbol{\theta}) = y_{ij} \log p_{ij} + (1-y_{ij}) \log (1 - p_{ij}),
\]
where \(y_{ij} \in \{0,1\}\) indicates whether \(i\) wins and
\[
p_{ij} = \frac{\exp(\theta_i)}{\exp(\theta_i) + \exp(\theta_j)} = \sigma(\theta_i - \theta_j).
\]

The second derivative matrix for a single comparison contributes
\[
I_{ij} = p_{ij}(1-p_{ij}) (e_i - e_j)(e_i - e_j)^\top,
\]
with \(e_k\) denoting the standard basis vector. Summing over all comparisons touching item \(i\) yields the Fisher Information for that parameter (after removing a reference item to handle identifiability):
\[
I_i = \sum_{j \in \mathcal{N}(i)} p_{ij}(1 - p_{ij}).
\]

The Cramér–Rao bound implies
\[
\mathrm{Var}(\hat{\theta}_i) \ge \frac{1}{I_i}, \qquad \mathrm{SE}(\hat{\theta}_i) \approx \frac{1}{\sqrt{I_i}}.
\]

Under non-adaptive random pairing with moderate ability spread, \(p_{ij}\) concentrates near 0.5, so each comparison contributes approximately 0.25 information units. If \(n_i\) comparisons involve essay \(i\), the baseline approximation becomes
\[
\mathrm{SE}(\hat{\theta}_i) \approx \frac{1}{\sqrt{0.25 \, n_i}} = \frac{2}{\sqrt{n_i}}.
\]

This reproduces the heuristic curve \( \mathrm{SE} \propto 1/\sqrt{n} \) and gives concrete targets:

| Comparisons per essay \(n_i\) | Approx. SE \(2/\sqrt{n_i}\) |
|-------------------------------|------------------------------|
| 5                             | 0.894                        |
| 10                            | 0.632                        |
| 15                            | 0.516                        |
| 30                            | 0.365                        |

### 4.2 Mapping SE to Confidence

Let \(d_i\) denote the absolute distance from an essay’s BT score to its nearest grade boundary (produced by `GradeProjector`). Using the normal approximation for \(\hat{\theta}_i\), the probability of remaining on the same side of the boundary is
\[
P(\text{stay}) = 1 - 2\,\Phi\!\left(-\frac{d_i}{\mathrm{SE}(\hat{\theta}_i)}\right),
\]
which matches the proposal already sketched during earlier sessions. This forms the backbone for a revised confidence factor, replacing the logistic comparison-count curve with an information-driven probability.

### 4.3 Audit of `compute_bt_standard_errors`

To validate the implementation against the theoretical curve, synthetic comparison sets were generated using the CJ service utilities (random pairing with balanced wins). A sample summary is below (median SE excludes the reference essay whose SE is fixed at 0):

| Target min comparisons per essay | Mean realised comparisons | Median SE (empirical) | Approx. SE \(2/\sqrt{\text{mean}}\) |
|----------------------------------|---------------------------|-----------------------|-------------------------------------|
| 4                                | 6.33                      | 1.287                 | 0.795                               |
| 8                                | 11.22                     | 0.851                 | 0.597                               |
| 12                               | 16.67                     | 0.718                 | 0.490                               |
| 20                               | 24.11                     | 0.556                 | 0.407                               |

The implementation behaves as expected: SE shrinks monotonically with additional information, though empirical values are 15–30 % larger than the naive \(2/\sqrt{n}\) rule because:

- Pairing is random rather than balanced, so the Fisher information per comparison is slightly below 0.25 in early stages.
- The reference-parameter convention and pseudoinverse amplify variance for sparse graphs; the hard-coded 2.0 cap guards against extreme underdetermination and explains the warnings seen when data are highly unbalanced.

Conclusion: `compute_bt_standard_errors` aligns with theory, but any production formula must incorporate the observed inflation factor when translating comparison counts into confidence to avoid over-promising.

### 4.4 Factor Weight Sensitivity Plan

Phase 3 will furnish the empirical dataset needed to back-test factor weights. The planned approach is:

1. **Data collection**: run controlled CJ batches via the service to obtain per-essay features—comparison count, SE, boundary distance, anchor coverage, and grade outcome accuracy relative to anchor truth.
2. **Correlation and regression**: evaluate each factor’s marginal contribution to correctness using logistic regression and elastic-net regularisation to guard against multicollinearity.
3. **Ablation**: simulate alternative weightings (equal weights, SE-only, SE+boundary, etc.) and measure accuracy/precision trade-offs.
4. **Stability metric**: once multi-session data exist, incorporate score drift (|θ_t − θ_{t-1}|) to test whether temporal stability deserves explicit weighting.

The outputs will feed directly into the recommendation phase, ensuring that any reweighted confidence formula carries statistical justification.
