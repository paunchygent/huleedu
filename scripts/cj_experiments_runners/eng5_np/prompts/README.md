# Prompt Versioning for Anchor Alignment Experiments

This directory contains versioned system prompts and rubrics for prompt tuning experiments.

## Directory Structure

```
prompts/
├── system/       # System prompt variants
│   └── 001_baseline.txt
├── rubric/       # Judge rubric variants
│   └── 001_baseline.txt
└── README.md
```

## Naming Convention

Files use sequential numbering: `{NNN}_{description}.txt`

- `001_baseline.txt` - Original/baseline version
- `002_anti_narrative.txt` - Hypothesis: reduce narrative style bias
- `003_ef_boundary.txt` - Hypothesis: clarify E/F grade boundary

## Usage

```bash
pdm run eng5-runner \
  --mode anchor-align-test \
  --system-prompt prompts/system/001_baseline.txt \
  --rubric prompts/rubric/001_baseline.txt \
  --batch-id "anchor-align-001" \
  --await-completion
```

## Report Filename Pattern

Reports are auto-generated with pattern:
`anchor_align_{batch_id}_{timestamp}.md`

## Metrics Tracked

| Metric | Description |
|--------|-------------|
| Direct inversions | Head-to-head where lower grade beats higher |
| Zero-win anchors | Anchors that lost ALL comparisons |
| Kendall's tau | Rank correlation with expected grade order |
| Per-anchor win rates | Individual anchor performance vs expected |
