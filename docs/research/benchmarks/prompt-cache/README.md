# Prompt Cache Benchmarks

## Overview

This directory contains benchmark results and analysis for Anthropic prompt caching effectiveness in the CJ Assessment service.

## Purpose

Evaluate the performance and cost benefits of Anthropic's prompt caching feature when processing comparative judgment assessments at scale.

## Methodology

### Benchmark Runner

**CLI**: `pdm run prompt-cache-benchmark`

**Key Parameters**:
- `--fixture`: `smoke` (4×4 = 16 comparisons) or `full` (10×10 = 100 comparisons)
- `--fixture-path`: Path to real fixture data (e.g., `data/eng5_smoke_fixture.json`)
- `--model`: LLM model (`claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929`)
- `--redact-output` / `--no-redact-output`: Control essay text inclusion in artefacts
- `--prom-url`: Prometheus pushgateway for metrics
- `--grafana-url`: Grafana dashboard URL for snapshot links

### Fixtures

1. **Synthetic Fixture** (default): Generated anchor/student essays for smoke testing
2. **ENG5 Real Fixture**: Extracted from Swedish national test data
   - Built via: `python -m scripts.prompt_cache_benchmark.build_eng5_fixture`
   - Locations: `data/eng5_smoke_fixture.json` (4×4), `data/eng5_prompt_cache_fixture.json` (full)

### Metrics Collected

- **Cache Performance**: hits, misses, bypass events
- **Token Usage**: cache read tokens, cache write tokens
- **Latency**: p50, p95, p99 response times
- **Cost**: Effective cost reduction from caching

## Directory Structure

```
prompt-cache/
├── README.md           # This file
├── runs/               # Individual benchmark run results (JSON + MD)
└── templates/          # Report templates
```

## Key Findings

### Model Compatibility

- **Haiku** (`claude-haiku-4-5-20251001`): Cache bypassed due to <2,048 cacheable tokens threshold
- **Sonnet** (`claude-sonnet-4-5-20250929`): Cache operational without prompt inflation

### ENG5 Smoke Test Results (2025-11-23)

**Latest Run** (Sonnet, 4×4, unredacted):
- Artefact: `runs/20251123T011800Z-prompt-cache-warmup.{json,md}`
- Cache hits: 16/16 (100%)
- Tokens read: 43,112 | Tokens written: 1,408
- Latency: p50=3.26s, p95=3.91s

## Artefact Files

Each benchmark run produces:
- `{timestamp}-prompt-cache-warmup.json`: Full raw data including LLM responses
- `{timestamp}-prompt-cache-warmup.md`: Human-readable summary with metrics

## References

- **Benchmark Implementation**: `scripts/prompt_cache_benchmark/`
- **Prompt Template Builder**: `services/cj_assessment_service/cj_core_logic/prompt_templates.py`
- **Anthropic Caching Docs**: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
