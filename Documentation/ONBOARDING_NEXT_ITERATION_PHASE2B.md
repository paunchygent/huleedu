# Onboarding – Batch Conductor Service Phase 2B

Welcome!  The previous iteration completed Kafka DLQ integration, dependency-injection wiring, containerisation, and green tests.  You will continue Phase 2B.

## What’s already done

1. `DlqProducerProtocol` and `KafkaDlqProducerImpl` implemented and injected.
2. API route `/internal/v1/pipelines/define` publishes to DLQ on failures and increments Prometheus counters.
3. In-memory No-Op DLQ producer used for local/testing to keep the suite Kafka-free.
4. Dockerfile + docker-compose entry for `batch_conductor_service` added; tests ( `pytest`, `mypy`) pass.

## Open work items

1. **Redis atomic update with Postgres hand-off**  
   • Implement WATCH/MULTI/EXEC transactions in `RedisCachedBatchStateRepositoryImpl`  
   • Introduce background worker that drains a Redis persistence queue to Postgres (design sketched in `TASKS/GATEWAY_BCS_IMPLEMENTATION_TASK.md`).  
   • Add retry/back-off and DLQ production on unrecoverable failures.
2. **Prometheus counters & histograms**  
   • Expose metrics for: redis transaction retries, postgres persistence successes/failures, DLQ messages produced, worker lag.  
   • Ensure they’re registered during `initialize_metrics` in `startup_setup.py`.
3. **Integration tests**  
   • Test happy-path persistence & forced transaction failures (use test-containers for Redis ‑> Postgres).  
   • Verify DLQ topic emission on failure.
4. **Documentation**  
   • Update service diagrams & README to reflect new persistence flow.

## Development advice

• Follow rules under `.windsurf/rules/040-service-implementation-guidelines.md` and metric naming conventions already documented.  
• Keep `ENV_TYPE` branching – Docker path must talk to real Redis/Postgres/Kafka, tests may use fakes.  
• Avoid `# type: ignore` / `noqa` except for unavoidable compatibility stubs.  
• All new code must be covered by tests (`pdm run pytest -q`).  
• Run `pdm run mypy` and `pdm run ruff` before committing.

Happy hacking – and keep the build green!
