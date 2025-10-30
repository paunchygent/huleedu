# D-Optimal Pair Selection Script Plan

## Objectives
- Produce an 84-comparison schedule that maximizes Fisher information for the Bradley–Terry consensus model while respecting anchor coverage and operational constraints.
- Retain compatibility with the existing redistribution utilities by emitting the same CSV schema (`pair_id, essay_a_id, essay_b_id, comparison_type, status`).
- Provide diagnostics that show the gain over the current hand-authored `session2_pairs.csv`.

## Inputs & Preprocessing
- **Posterior snapshot**: Current student ability estimates, standard errors, and pair history (from `essay_consensus.csv` and session 1 logs).
- **Anchor catalogue**: Ordered list of anchor essays with grade levels and identifiers (e.g., `ANCHOR_DISPLAY` mapping).
- **Rater roster**: Optional list to keep per-rater calibration pairs in the final export.
- Build a canonical node index (students first, anchors second) so the optimizer can address the parameter vector consistently.
- Construct the universe of allowable pairs (student–anchor, student–student, anchor–anchor); flag already-observed pairs so we can weight repeated matchups.

## Optimization Strategy
1. **Seed design**  
   - Start from a minimal connected set that satisfies basic coverage (each student bracketing anchor below/near/above; each anchor appears ≥1×).  
   - Record the initial Fisher information matrix `I0`.
2. **Greedy expansion**  
   - Iteratively add candidate pairs that maximize `det(I_k + ΔI)` until reaching 84 slots or hitting hard constraints.  
   - For tied gains, prefer pairs that reduce the largest posterior variance or add new rater overlap.
3. **Fedorov-style exchange**  
   - With a full design in place, iterate over (in-pool, out-of-pool) swaps that increase the log-determinant while keeping coverage constraints satisfied.  
   - Stop when no improving exchange exists within tolerance or after N iterations.
4. **Constraint enforcement**  
   - Hard constraints: minimum anchor exposure per grade, min student–anchor brackets per student, max repetitions of the same ordered pair.  
   - Soft penalties: encourage at least one shared calibration comparison per rater (if roster supplied) and bias toward covering high-uncertainty essays.

## Implementation Notes
- Represent each candidate as a sparse column in the design matrix; pre-compute ΔI contributions so swapping remains O(p²) instead of recomputing from scratch.
- Keep the algorithm deterministic by wiring a seed through any shuffle or tie-break logic.
- Allow CLI arguments to toggle constraint weights, the uncertainty weighting function, and the maximum repeat count.

## Outputs
- `optimized_pairs.csv`: final 84-row schedule with core status.  
- `optimized_pairs_extra.csv`: optional reserve list ranked by marginal information gain.  
- `optimization_report.json`: metrics including log-det gain vs. baseline, per-node exposure counts, calibration overlap summary, and constraint violations (if any).
- Automatically render plots (e.g., heatmap of pair coverage, info gain per comparison) into `output/bayesian_consensus_model/<timestamp>/`.

## Validation Checklist
- Recompute Fisher information for the optimized schedule and confirm the determinant improves over the current hand-crafted design.
- Verify coverage tables: every student hits required anchor brackets; anchors meet appearance minimums; low-confidence essays receive elevated coverage.
- Run a dry-run Bayesian update using synthetic outcomes to ensure the schedule is graph-connected and numerically stable.
- Spot-check exported CSV with `redistribute_core.read_pairs` to guarantee downstream tools accept the new plan.

## Constraint & Calibration Decisions
- **Anchor adjacency coverage**: Treat anchor grade neighbors as hard constraints—every interior anchor must appear in at least one comparison with both the next-lower and next-higher anchor grade (top/bottom anchors only require the single available neighbor). This keeps the grade ladder connected even if student-anchor slots are reallocated.
- **Student bracket coverage**: Derive a below/near/above anchor set for each student from the baseline schedule and require those three anchors (or all available if fewer) to appear at least once per student in the optimized design. This preserves the scale-linking guarantees while letting the optimizer assign additional comparisons where they add the most information.
- **High-information duplicates**: Treat repeat appearances of critical threshold pairs as part of the optimization objective—not fixed allocations—so the algorithm can replicate them when they increase Fisher information without consuming large chunks of the budget on identical comparisons.

## CLI Integration Plan
1. **Expose optimizer via Typer**  
   - Add a new command (e.g., `optimize-pairs`) to `redistribute_pairs.py` or a companion CLI that accepts session paths, rater roster, calibration toggle, and output destination.  
   - Surface knobs for `max-repeat`, seed, and optional exclusion of calibration pairs.
2. **Leverage existing serialization**  
   - Reuse `write_assignments` or new helper to emit optimized schedules in the same schema, including optional flags to split calibration vs. core comparisons for post-processing.  
   - Provide summary stats (log-det gain, type counts) in the CLI output for operator validation.
3. **Workflow integration**  
   - Extend documentation (`README.md` and session planning notes) with instructions for running the optimizer before redistribution.  
   - Ensure the new command plugs into the TUI and Typer pipelines, allowing teams to regenerate rater assignments directly after optimization.
