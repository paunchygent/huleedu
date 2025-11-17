# Task: CJ LLM Serial Bundling

## Summary
Implement the serial-bundling exploration described in `.claude/research/anthropic-openai-batch.md` & `.claude/tasks/TASK-LLM-BATCH-STRATEGY.md` (items 2–5). Introduce a new `LLM_BATCHING_STRATEGY` setting (defaulting to the “serial per-round” mode) with an optional override integer for `max_comparisons` bundles. The architectural goal is for each `perform_comparisons` invocation to result in a single multi-prompt provider request, but that bundling happens inside the LLM Provider Service queue/adapter layer (CJ still sends one request per `ComparisonTask`). The provider adapter should send one multi-prompt call (bounded by the configured bundle size) to Anthropic/OpenAI, fan the ordered/mapped results back into per-comparison callbacks, and keep the existing Kafka payload shape intact.

## References
- `.claude/research/anthropic-openai-batch.md`: Anthropic + OpenAI batching capabilities, prompt reuse, metadata requirements.  
- `.claude/tasks/TASK-LLM-BATCH-STRATEGY.md`: High-level rollout (config, serial bundling, batch helper, provider hooks, metrics).  
- `services/cj_assessment_service/cj_core_logic/batch_processor.py`: How comparison rounds are chunked and passed to `LLMInteractionImpl`.  
- `services/cj_assessment_service/implementations/llm_interaction_impl.py`: Entry point that currently issues one HTTP call per `ComparisonTask`.  
- `services/llm_provider_service/implementations/queue_processor_impl.py`: Where queued requests are pulled and provider calls emitted.  
- `libs/common_core/src/common_core/events/llm_provider_events.py`: `LLMComparisonResultV1` schema that must still be emitted per comparison.

## Goals
1. **Serial bundling helper** – Update the queue processor (or optionally CJ entry point) to:
   - Group up to the configured bundle size (default `max_comparisons`, overridable per request) of pending CJ requests that share provider/model/round context.
   - Build a provider-specific multi-prompt payload (Anthropic JSON list, OpenAI multi-input) using the existing prompt builder + `request_metadata`.
   - Send one API call, parse the list of responses (each with `correlation_id`/`custom_id`), and emit one `LLMComparisonResultV1` callback per original comparison.
2. **Batching strategy configuration** – Introduce `LLM_BATCHING_STRATEGY` in `services/cj_assessment_service/config.py` with modes:
   - `serial_round` (default): bundle the current `perform_comparisons` round up to `MAX_CONCURRENT_COMPARISONS`.
   - `serial_override`: allow a request-level integer to override the bundle size (e.g., send all `max_comparisons` vs. a smaller chunk).
   - `nightly_batch`/`async_batch`: future modes for multi-round accumulation or provider async APIs (documented but out of scope for this ticket).
   Propagate the selected strategy through `BatchProcessor`/`LLMInteractionImpl` so the queue processor knows how many items to bundle.
3. **Metadata contract** – Ensure every comparison request (queued and callback) carries:
   - `request_correlation_id` (the canonical key / `custom_id`).
   - `essay_a_id`, `essay_b_id`, `cj_batch_id`, optional `bos_batch_id`.
   - `prompt_sha256` (from `services/llm_provider_service/prompt_utils.compute_prompt_sha256`).
   - Optional `bundle_id`/`bundle_index` to debug grouping.
4. **Callback preservation** – Keep the Kafka schema unchanged (`LLMComparisonResultV1`) and continue publishing one event per comparison; the watcher should link each bundled response to the `request_correlation_id` and existing CJ database row (see `services/cj_assessment_service/models_db.py`).
5. **Metrics clarity** – Document that queue depth/health metrics remain per comparison unless we later introduce bundle-as-job queue entries; add extra metrics only if the queue model changes.

## Implementation stages
1. **Config + strategy wiring** – Add the new `LLM_BATCHING_STRATEGY` setting, expose per-request override hooks (maybe via metadata on `submit_batch_chunk`), and ensure `LLMInteractionImpl` passes the bundle size limit to the provider client.
2. **Queue bundler** – Modify `queue_processor_impl` to peek at `LLM_BATCHING_STRATEGY`, pull the appropriate number of `QueuedRequest`s, send a single multi-prompt provider call, and distribute the ordered callback responses.
3. **Metadata enforcement** – Ensure every `request_metadata`/`LLMComparisonResultV1.request_metadata` entry includes the defined spine and optional bundle tags so both serial and future async bundles are traceable.
4. **Docs & tracing** – Update `.claude/tasks/TASK-LLM-BATCH-STRATEGY.md` to reference this ticket, note the default serial mode, and include instructions on how to switch to override/nightly modes.

## Deliverables
- Updated queue processor that can bundle multiple CJ comparisons into a single provider call and still fan out callbacks.  
- Documentation or config flag showing which `cj_settings.llm_batching_strategy` modes are supported (serial bundling default, nightly job future).  
- An annotated mapping note (maybe a doc section) describing how provider responses (ordered list or `custom_id` array) map to `ComparisonTask`s.  
- Confirmation that CJ event consumers continue to see the same fields they already rely on (`correlation_id`, `winner`, `confidence`, `request_metadata`).  

## Next actions
1. Prototype bundling inside `services/llm_provider_service/implementations/queue_processor_impl.py`, referencing the files above for how requests are queued and callbacks emitted.  
2. Update `request_metadata` creation in `LLMInteractionImpl` so it includes the full metadata spine and optionally `bundle_id`.  
3. Add a doc block in `.claude/tasks/TASK-LLM-BATCH-STRATEGY.md` referencing this ticket as the serial bundling implementation step and point to the research note.  
4. After prototyping, evaluate whether the same approach can be reused for asynchronous batch jobs or whether a separate watcher is needed.  
