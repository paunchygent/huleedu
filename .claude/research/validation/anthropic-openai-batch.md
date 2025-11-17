# Anthropic + OpenAI batch research

## Anthropic (Haiku 4.5 and Sonnet 4.5)
- Model manifest already lists `claude-haiku-4-5-20251001` and `claude-sonnet-4-5-20250929` with structured-output, tool-use, and vision support, so our service can target the exact same identifiers that the API expects today.
- The public Message Batches API (`POST /v1/messages/batches`) accepts between 1 and 10,000 individual request objects per HTTP call but may cover up to 100,000 total requests (and 256 MB) across a single batch job, so large workloads should be chunked or parallelized. Each request is a standard Claude Messages payload (system/user messages, tools, etc.), so we can reuse the same prompt builder that presently feeds single comparisons.
- Batch jobs benefit from the existing rate limits/discounted pricing (processing within 24 hours, 50% token cost savings, shared batch queue rate caps), and Anthropic encourages mixing vision, tool use, and beta features within the same batch, which keeps our structured JSON schema intact even when more context is added.

## OpenAI Batch API
- OpenAI requires uploading a `purpose=batch` JSONL file first and then creating a batch via `POST /v1/batches` with the `input_file_id`, the target endpoint (e.g., `/v1/chat/completions`), and a completion window (currently 24h). Each JSONL line must include `custom_id`, `method`, `url`, and a `body` that mirrors the usual request payload (same `model`, `messages`, `gpt-4o-mini`, etc.).
- The uploaded file may hold up to 50,000 requests and 200 MB; all lines in that file must target the same endpoint and model, so we would emit one JSONL per model/round. Batches complete asynchronously (within 24 hours, often sooner) and cost 50% less than the synchronous API while enjoying higher rate limits, which makes them ideal for nightly CJ scoring jobs.

## Bundled serial calls (before asynchronous batches)
- OpenAI’s normal API already has a “batching requests” best practice: you can send multiple prompts inside a single Chat/Completion call (`prompt` can be a list of strings or JSON inputs). That lets you drop RPM pressure by reducing the number of HTTP requests as long as you stay within the model’s token limit, but it requires post-processing the ordered/haphazard responses. citeturn4search0
- Anthropic’s docs likewise recommend “batching similar requests” into one Claude message if you have multiple related items to compare, so you can keep hitting your normal RPM budget without setting up the asynchronous Message Batches API. citeturn9search3

## CJ settings implications
- The CJ workflow currently builds one prompt per pair and immediately fires it through `LLMInteractionImpl`, so “per-round” batching would mean collecting each round’s tasks, mapping them to `custom_id`s, and either (a) sending them together via a serial multi-prompt call, or (b) dropping them into a single asynchronous batch job.  
- We should expose a setting (`cj_settings.llm_batching_strategy` or similar) defaulting to “round-level batching while still issuing one HTTP call per comparison”) with additional modes for “nightly job” or “accumulate until N pairs” before submitting job‐wide batches.
## Notes for integration
- Our current prompt builder already packages two essays, rubric, and JSON-output instructions inside `ComparisonTask.prompt`, so we can reuse that content when materializing each batch entry.
- Delivering batch results will require a watcher that polls the batch status and emits Kafka callbacks once each `custom_id` is resolved—this is a new responsibility for the provider service.
