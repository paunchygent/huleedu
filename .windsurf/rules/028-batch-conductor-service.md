---
description: "Rules for the Batch Conductor Service (BCS). Defines architecture, state-tracking model, metrics, and mandatory patterns."
globs:
  - "services/batch_conductor_service/**/*.py"
alwaysApply: true
---

# 028: Batch Conductor Service Architecture

## 1. Service Identity

| Property | Value |
|----------|-------|
| **Package** | `huleedu-batch-conductor-service` |
| **Port** | 5050 (HTTP + metrics) |
| **Stack** | Quart, aiokafka, Redis, PostgreSQL, Dishka, Prometheus |

**Purpose** – Single source-of-truth for essay-batch pipeline state. Resolves pipeline step order, tracks completion counts, and tells BOS / ELS what to execute next.

---

## 2. Core Components & Clean-Architecture Layout

services/batch_conductor_service/ ├── app.py # Lean Quart entry (<50 LOC) ├── startup_setup.py # DI init + metrics + graceful shutdown ├── implementations/ │ ├── batch_state_repository_pg_impl.py # Postgres persistence │ ├── batch_state_repository_redis_cache.py # Redis hot-cache layer │ ├── pipeline_generator_impl.py # YAML loader & validation │ ├── pipeline_rules_impl.py # Dependency resolution & pruning │ └── pipeline_resolution_service_impl.py # Facade used by BOS ├── protocols.py # typing.Protocol definitions ├── di.py # Dishka providers ├── config.py # Pydantic Settings └── kafka_consumer.py # Event handlers (DLQ, etc.)

*All external interactions (DB, Redis, Kafka, HTTP) are injected via `typing.Protocol` interfaces and wired by Dishka.*

---

## 3. Persistence & State-Tracking Model

* **Redis Hash per batch**:  
  `key = f"batch:{batch_id}:pipeline_state"`  
  `field = step_name`, `value = completed_count:int`

* **PostgreSQL table `processing_pipeline_state`** mirrors Redis for durability.

* **Atomicity** – use Redis `WATCH/MULTI` (or Lua script) to guard concurrent [step_complete](cci:1://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/batch_conductor_service/protocols.py:68:4-79:11) writes.

* **Completion rule** – a step is `COMPLETE` when `completed_count == essays_total`.

---

## 4. Dependency Resolution Flow

1. **Pipeline YAML** loaded once by [DefaultPipelineGenerator](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/batch_conductor_service/implementations/pipeline_generator_impl.py:17:0-146:17) (cycle detection + unknown-step validation).  
2. **DefaultPipelineRules**  
   * Builds sub-graph from requested step  
   * Performs topological sort  
   * Optionally calls [prune_completed_steps](cci:1://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/batch_conductor_service/implementations/pipeline_rules_impl.py:99:4-108:30) (uses [BatchStateRepository](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/batch_conductor_service/protocols.py:18:0-79:11))  
   * Exposes [validate_pipeline_prerequisites()](cci:1://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/batch_conductor_service/implementations/pipeline_rules_impl.py:78:4-97:19) for BOS gating.  
3. **DefaultPipelineResolutionService** – thin facade consumed by BOS & external callers.

---

## 5. Observability & Metrics

Metric | Type | Description
------ | ---- | -----------
`bcs_pipeline_config_load_success_total` | Counter | Successful YAML loads
`bcs_pipeline_config_load_error_total` | Counter | YAML load/validation failures
`bcs_pipeline_rules_success_total` | Counter | Successful dependency resolutions
`bcs_pipeline_rules_error_total` | Counter | Resolution errors
`bcs_pipeline_rules_pruned_total` | Counter | Steps pruned because already complete

All metrics are registered in a `CollectorRegistry` injected via Dishka; `/metrics` endpoint served by shared Prometheus middleware.

---

## 6. Kafka Dead-Letter Handling

Messages failing JSON / schema validation or raising unrecoverable processing errors must be produced to a `.dlq` topic with envelope:

```json
{
  "original_topic": "...",
  "timestamp": "...",
  "schema_version": "v1",
  "payload": { ... },
  "error_info": "traceback / validation messages"
}
kafka_consumer.py
 MUST acknowledge or DLQ within the same consumer group session.

7. Dependency Injection & Startup Rules
Construct container = build_container() in 
startup_setup.py

**MANDATORY** – call QuartDishka(app, container) before registering any blueprint that uses @inject.
Register blueprints, then start Hypercorn via hypercorn.run().

8. Testing & Quality Assurance
Unit tests (pytest + pytest-asyncio) must mock 
BatchStateRepository
 & 
PipelineGenerator
 using unittest.mock.AsyncMock or custom fakes implementing the Protocols.
Property tests with Hypothesis generate random DAGs to ensure cycle detection and stable topological ordering.
Linting via Ruff; run pdm run ruff . in CI.
All test suites executed with pdm run pytest -q.

9. Mandatory Production Patterns
Graceful shutdown – ensure Kafka consumer, Redis pool, and DB engine close in 
startup_setup.py

Idempotency – Redis SETNX or Lua scripting around step-completion writes.

Fail fast – critical startup errors must logger.critical() then raise.

No hard-coded Kafka topic names – always use common_core.enums.topic_name() helper.

---
