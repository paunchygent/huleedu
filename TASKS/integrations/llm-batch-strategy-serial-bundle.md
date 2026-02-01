---
id: llm-batch-strategy-serial-bundle
title: Llm Batch Strategy Serial Bundle
type: task
status: done
priority: high
domain: integrations
owner_team: agents
created: '2025-11-21'
last_updated: '2026-02-01'
service: llm_provider_service
owner: ''
program: ''
related: []
labels: []
---

# Task: LLM batching strategy

## Reference
- Research notes: `.claude/research/anthropic-openai-batch.md`

## High-level tasks
1. **CJ batching config** – Add `cj_settings.llm_batching_strategy` (or equivalent) that defaults to “per-round batching that aggregates the comparison tasks generated within a single `perform_comparisons` call and submits them together,” but which can switch to “accumulate multiple rounds before dispatching a nightly batch job.” Include settings for both Anthropic and OpenAI providers in `CJ assessment service` config.
2. **Serial-bundled prototype** – Before introducing async batches, prototype bundling several comparison prompts into one sequential API call (either by sending multiple `messages` entries to Claude/OpenAI or pushing multiple prompts through a single `prompt` list) so we can measure whether reducing HTTP operations eases the current rate-limit pressure. Track any custom mapping between essay pairs and the provider’s response order.
3. **Batch job helper** – Build a helper that maps each `ComparisonTask` → `custom_id`, writes JSONL for OpenAI or the appropriate payload for Anthropic Message Batches, uploads it, and polls the resulting job; keep using the current prompt builder so `winner/justification/confidence` schema stays the same.
4. **Provider service hooks** – Extend the `LLMProviderService` queue/processor to treat batch jobs as “queued”—the callback emitter should wait for every `custom_id` result, translate it back to the originating essay pair, and emit the same Kafka events (no quarterly contract change).  
5. **Metrics + rate-limit tracking** – Log batch progress and rate-limit stats, so we can compare per-round batching, serial bundling, and nightly jobs. This includes new health metrics for pending batches and watchers for the queue processor that currently handles single requests.
