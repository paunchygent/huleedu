# TASK-052C — Java LanguageTool Wrapper & Grammar Filtering

## Objective

Wrap the LanguageTool Java library with a managed subprocess that returns structured matches filtered to grammar categories only.

## Boundary Objects & Contracts

- Protocol: `LanguageToolWrapperProtocol.check_text(text, language) -> list[GrammarError]`
- Filtering rules (server‑side): Exclude categories: `TYPOS`, `MISSPELLING`, `SPELLING` (optionally `STYLE`, `TYPOGRAPHY` per product decision). Maintain a config allow/deny list.
- Timeouts: Max 30s per request; queue concurrency via `asyncio.Semaphore`.

## Shared Libraries

- `asyncio`, `subprocess` management
- `huleedu_service_libs.error_handling` (structured errors)
- `prometheus_client` for wrapper timing metrics

## Implementation Steps

1. Download/bundle LanguageTool jar in image layer (or mount).
2. Implement wrapper lifecycle (start on APP scope; stop on shutdown).
3. Implement request/response bridge (stdin/stdout JSON or HTTP to embedded LT server) with timeout.
4. Map LanguageTool match → enhanced `GrammarError` fields (Subtask A):
   - `rule.id → rule_id`
   - `category.id/name → category_id/category_name`
   - `context.text/offset → context/context_offset`
   - `offset/length/replacements/message/issueType → existing fields`
5. Apply category filtering and build counters (category/rule).
6. Emit wrapper metrics and logs with correlation id.

## Acceptance Tests

- Happy path: returns filtered matches; counts computed.
- Timeout path: operation aborts and returns structured error.
- OOM/restart: wrapper recovers after simulated failure.

## Risks & Mitigation

- JVM memory spikes → bounded heap via JAVA_OPTS; restart policy.
- Latency variance → per‑request timeout + concurrency limits.

## Deliverables

- Wrapper implementation with tests and documentation of filtering rules.

