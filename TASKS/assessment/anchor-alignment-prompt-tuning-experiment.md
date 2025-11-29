---
id: 'anchor-alignment-prompt-tuning-experiment'
title: 'Anchor Alignment Prompt Tuning Experiment'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: 'eng5'
created: '2025-11-29'
last_updated: '2025-11-29'
related: ['TASKS/assessment/bt-se-zero-anomaly-and-anchor-inversions-investigation.md']
labels: ['research', 'prompt-engineering', 'calibration']
---

# Anchor Alignment Prompt Tuning Experiment

## Implementation Status

### Completed (2025-11-29)

| Component | Location | Description |
|-----------|----------|-------------|
| `judge_rubric_override` field | `libs/common_core/.../cj_assessment_events.py:108-111` | Added to `LLMConfigOverrides` for per-request rubric override |
| Rubric override threading | `services/cj_assessment_service/.../batch_preparation.py:198-210` | Applied before metadata storage, flows to prompt composition |
| `ANCHOR_ALIGN_TEST` mode | `scripts/.../eng5_np/settings.py:20` | New `RunnerMode` enum value |
| Settings fields | `scripts/.../eng5_np/settings.py:49-53` | `system_prompt_file`, `rubric_file`, `system_prompt_text`, `rubric_text` |
| CLI options | `scripts/.../eng5_np/cli.py:416-426` | `--system-prompt PATH`, `--rubric PATH` |
| Mode execution flow | `scripts/.../eng5_np/cli.py:632-745` | Full anchor-align-test pipeline with GUEST behavior |
| `alignment_report.py` | `scripts/.../eng5_np/alignment_report.py` | Report generator with Kendall's tau, inversions, per-anchor metrics |
| `load_anchor_grade_map` | `scripts/.../eng5_np/artefact_io.py:178` | Exported for alignment report |
| Prompt versioning | `scripts/.../eng5_np/prompts/` | Directory structure with baseline prompts |

### Refactoring Complete (2025-11-29)

CLI refactored to handler-based architecture:
- `cli.py` reduced from 926 → 569 lines (handler dispatch pattern)
- `--assignment-id` now optional (required only for EXECUTE mode)
- All modes delegate to dedicated handler classes

| Component | Lines | Location |
|-----------|-------|----------|
| cli.py | 569 | Main CLI, handler dispatch |
| protocols.py | ~130 | `ModeHandlerProtocol`, `RunnerSettingsProtocol` |
| plan_handler.py | 103 | PLAN mode |
| dry_run_handler.py | 73 | DRY_RUN mode |
| anchor_align_handler.py | 251 | ANCHOR_ALIGN_TEST mode |
| execute_handler.py | 342 | EXECUTE mode |

**Tests:**
- 51 unit tests for `alignment_report.py` ✓
- typecheck-all passes ✓
- lint passes ✓

**Outstanding:**
- Handler tests (pending)
- CLI integration tests (pending)
- anchor_align_handler.py and execute_handler.py exceed 200-line target (future improvement)

### Ready for Baseline Experiment

| Task | Priority | Description |
|------|----------|-------------|
| **Run baseline experiment** | High | Execute anchor-align-test with baseline prompts, establish metrics |
| **Create experiment prompts** | High | Develop hypothesis-driven prompt variants (anti-narrative, E/F boundary, etc.) |
| **Run prompt comparison experiments** | High | Iterate through prompt variants, measure alignment changes |
| **Document findings** | Medium | Create experiment report with conclusions and recommendations |

---

## Objective

Create an isolated, repeatable test harness for tuning LLM judge prompts to improve alignment between LLM comparative judgments and expert-graded anchor essays.

**Hypothesis:** Better LLM-expert alignment can be achieved through prompt engineering of the assessment instructions and judge rubric, without requiring model upgrades or additional compute.

## Why This Exists

### Problem Statement

Investigation of batch 108 (ENG5 NP Role Models) revealed systematic anchor inversions:

| Region | Alignment Status |
|--------|------------------|
| A/B grades | Correct calibration |
| C-/D/E/F grades | Systematic misalignment |

**Key findings:**
- ANCHOR_7 (E-) won 0 of 17 comparisons (lost to both F+ anchors)
- ANCHOR_3 (C-) and ANCHOR_11 (E+) have identical win rates (25%) despite 3-grade gap
- LLM favors narrative structure and argumentation breadth over expert criteria
- Expert graders use subject-specific E/F boundary criteria not captured in current rubric

**Root cause:** LLM holistic "better" judgment systematically diverges from expert grading criteria in the lower grade range.

### Why an Isolated Test Harness?

1. **Controlled variable isolation:** Only anchors (known grades) are compared - no student essay noise
2. **Fast iteration:** 12 essays = 66 pairs, ~2-5 minutes per run, ~$0.10 cost
3. **Clear ground truth:** Expert grades are authoritative
4. **No side effects:** GUEST flow (`assignment_id=None`) bypasses DB anchors and grade projection

## Method

### Architecture

```
+------------------+     +------------------+     +------------------+
| 12 Anchor Essays |---->| GUEST Flow       |---->| CJ Assessment    |
| (known grades)   |     | assignment_id=   |     | Service          |
|                  |     | None             |     |                  |
+------------------+     +------------------+     +--------+---------+
                                                          |
                                                          v
+------------------+     +------------------+     +------------------+
| Alignment Report |<----| Report Generator |<----| BT Scores +      |
| (markdown)       |     | (alignment_      |     | Win/Loss Matrix  |
+------------------+     | report.py)       |     +------------------+
                         +------------------+
```

### Data Flow for `judge_rubric_override`

```
LLMConfigOverrides.judge_rubric_override
    → batch_preparation.py:create_cj_batch() [APPLIED HERE]
    → batch.processing_metadata["judge_rubric_text"]
    → pair_generation.py:_fetch_assessment_context()
    → prompt_templates.py (prompt composition)
```

### CLI Usage

```bash
# Baseline run
pdm run eng5-runner \
  --mode anchor-align-test \
  --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/001_baseline.txt \
  --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/001_baseline.txt \
  --batch-id "anchor-align-baseline" \
  --await-completion

# Experiment with anti-narrative prompt
pdm run eng5-runner \
  --mode anchor-align-test \
  --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/002_anti_narrative.txt \
  --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/001_baseline.txt \
  --batch-id "anchor-align-002" \
  --await-completion
```

### Prompt Versioning Structure

```
scripts/cj_experiments_runners/eng5_np/prompts/
├── system/
│   ├── 001_baseline.txt       # Current production system prompt
│   ├── 002_anti_narrative.txt # "Narrative style does not indicate quality"
│   └── 003_ef_boundary.txt    # Explicit E/F boundary guidance
├── rubric/
│   ├── 001_baseline.txt       # Current production rubric
│   ├── 002_task_focus.txt     # Emphasize prompt point coverage
│   └── 003_l2_framing.txt     # "For L2 learner at this level"
└── README.md
```

## Success Criteria

| Metric | Baseline (Batch 108) | Target | Description |
|--------|----------------------|--------|-------------|
| Direct inversions | 5 | ≤1 | Head-to-head where lower grade beats higher |
| Zero-win anchors | 1 (ANCHOR_7) | 0 | No anchor should lose ALL comparisons |
| Kendall's tau | ~0.82 | ≥0.90 | Rank correlation with expected grade order |
| A/B regression | 0 | 0 | Upper grade calibration must not degrade |

## Prompt Engineering Hypotheses

| ID | Hypothesis | Prompt Change | Expected Impact |
|----|------------|---------------|-----------------|
| H1 | Grade boundary awareness | Add explicit E/F boundary description | Reduce E-/F+ inversions |
| H2 | Task fulfillment focus | Emphasize "addresses all prompt points" over structure | Improve C-/D alignment |
| H3 | L2 context framing | Add "for L2 learner at this level" framing | Better calibration of error tolerance |
| H4 | Anti-narrative bias | Explicitly state "narrative style does not indicate quality" | Reduce structural bias |

## Baseline Data (Batch 108)

### Win-Loss Statistics

| Anchor | Grade | Wins | Losses | Total | Win Rate | BT Score | Expected | Actual |
|--------|-------|------|--------|-------|----------|----------|----------|--------|
| ANCHOR_12 | A | 14 | 3 | 17 | 82% | 3.72 | 1 | 1 |
| ANCHOR_10 | A | 12 | 5 | 17 | 71% | 2.31 | 2 | 4 |
| ANCHOR_2 | B | 12 | 5 | 17 | 71% | 2.95 | 3 | 2 |
| ANCHOR_5 | B | 12 | 5 | 17 | 71% | 2.94 | 4 | 3 |
| ANCHOR_6 | C+ | 7 | 10 | 17 | 41% | -0.03 | 5 | 5 |
| ANCHOR_3 | C- | 4 | 12 | 16 | 25% | -1.99 | 6 | 7 |
| ANCHOR_9 | D+ | 6 | 10 | 16 | 38% | -1.88 | 7 | 6 |
| ANCHOR_8 | D- | 3 | 14 | 17 | 18% | -4.05 | 8 | 9 |
| ANCHOR_11 | E+ | 4 | 12 | 16 | 25% | -3.24 | 9 | 8 |
| ANCHOR_7 | E- | 0 | 17 | 17 | 0% | -7.99 | 10 | 12 |
| ANCHOR_4 | F+ | 2 | 15 | 17 | 12% | -5.04 | 11 | 10 |
| ANCHOR_1 | F+ | 1 | 16 | 17 | 6% | -6.31 | 12 | 11 |

### Direct Inversions (5 total)

| Higher Grade | Lower Grade | Winner | Confidence | Justification |
|--------------|-------------|--------|------------|---------------|
| ANCHOR_10 (A) | ANCHOR_2 (B) | B | 3.5 | "Better addresses assignment scope" |
| ANCHOR_10 (A) | ANCHOR_5 (B) | B | 4.0 | "Stronger structure" |
| ANCHOR_8 (D-) | ANCHOR_11 (E+) | E+ | 3.5 | "Clearer structure, deeper analysis" |
| ANCHOR_7 (E-) | ANCHOR_1 (F+) | F+ | 3.5 | "Better structure, more rubric points" |
| ANCHOR_7 (E-) | ANCHOR_4 (F+) | F+ | 3.5 | "Discusses influence on values" |

## Constraints

- **Cost:** Optimize on Haiku first (baseline ~$0.10/run for 66 pairs)
- **Time:** Each test run should complete in <5 minutes
- **Simplicity:** GUEST flow (`assignment_id=None`), no anchor/projection logic in test path
- **Isolation:** Prompt changes should not require code changes

## Related

- Root cause analysis: `TASKS/assessment/bt-se-zero-anomaly-and-anchor-inversions-investigation.md`
- Current rubric: `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/llm_prompt_cj_assessment_eng5.md`
- System prompt: `scripts/cj_experiments_runners/eng5_np/system_prompt.py`
- ENG5 runner: `scripts/cj_experiments_runners/eng5_np/cli.py`

## Notes

- GUEST flow (`assignment_id=None`) bypasses anchor registration and grade projection
- Full round-robin (66 pairs) provides complete picture but costs more
- Report generator includes full prompt text for reproducibility
- Prompt versions tracked in `scripts/cj_experiments_runners/eng5_np/prompts/` directory
