---
description: "Rules for the Spell Checker Service. Ensures consistent text processing in an event-driven architecture."
globs: 
  - "services/spell_checker_service/**/*.py"
alwaysApply: true
---
# 022: Spell Checker Service Architecture

## 1. Service Identity

- **Package**: `huleedu-spell-checker-service`
- **Type**: Combined Service (Kafka Worker + HTTP Health API)
- **Stack**: `aiokafka`, `aiohttp`, `quart`, `dishka`
- **Purpose**: Event-driven spell checking with health monitoring.

## 2. Architectural Mandates

### 2.1. Combined Service Pattern

- **MUST** run both the Kafka worker and health API concurrently using `run_service.py`.
- The HTTP API (`app.py`) **MUST** only provide `/healthz` and `/metrics` endpoints via the `health_routes` Blueprint.
- The worker entrypoint **MUST** be `worker_main.py`.

### 2.2. Clean Architecture & DI

- Business logic **MUST** be separated into:
  - `event_processor.py`: Orchestrates the fetch-process-store-publish workflow for a single message.
  - `core_logic.py`: Contains pure, reusable algorithms (e.g., `default_perform_spell_check_algorithm`).
  - `protocol_implementations/`: Contains all concrete implementations of protocols.
- All dependencies **MUST** be defined as interfaces in `protocols.py` and injected via Dishka providers in `di.py`.

## 3. Event Contracts

- **MUST Consume**: `huleedu.essay.spellcheck.requested.v1` with an `EventEnvelope[EssayLifecycleSpellcheckRequestV1]` payload.
- **MUST Publish**: `huleedu.essay.spellcheck.completed.v1` with an `EventEnvelope[SpellcheckResultDataV1]` payload.
- **Consumer Group ID**: MUST be configured via `CONSUMER_GROUP` in `config.py`.

## 4. Integration & Logic Requirements

- **Content Service**: All interactions **MUST** go through the `ContentClientProtocol` and `ResultStoreProtocol`.
- **Language Parameter**: The core spell check logic **MUST** accept and use the `language` parameter from the `EssayLifecycleSpellcheckRequestV1` payload.
- **Kafka Client**: Kafka interactions **MUST** use the shared `KafkaBus` from `huleedu-service-libs` for publishing. The consumer **MUST** use manual offset commits.

## 5. Configuration & Deployment

- **Configuration**: All settings **MUST** be defined in `config.py` using Pydantic `BaseSettings` with the `SPELL_CHECKER_SERVICE_` prefix.
- **Deployment**: The Docker container **MUST** use `pdm run start_service` as its `CMD` to launch the combined service.
- **Health Check**: The Docker health check **MUST** target the `/healthz` endpoint on the exposed health API port (8002).
