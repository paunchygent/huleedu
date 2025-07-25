# **Epic: Implement Transactional Outbox Pattern via Shared Library**

**Ticket ID:** `ARCH-012`
**Type:** Epic
**Assignee:** Tech Lead, Core Services Team
**Reporter:** CTO

## **1. Summary**

To guarantee reliable event delivery and prevent data inconsistency across our microservices, we will implement the Transactional Outbox pattern. This will be achieved by creating a robust, shared library (`huleedu-outbox-relay`) that provides a standardized implementation for all Kafka-publishing services.

This initiative decouples our services' core business logic from the availability of the Kafka message broker, ensuring that database updates and their corresponding event publications are atomic.

## **2. Acceptance Criteria**

- A new shared library, `huleedu-outbox-relay`, exists within `libs/huleedu_service_libs/`.
- The library provides a generic `EventOutbox` SQLAlchemy model, a `PostgreSQLOutboxRepository`, a configurable `EventRelayWorker`, and a `Dishka` provider for easy integration.
- The **File Service** is the first service to be fully migrated to use the new outbox library for its critical events.
- Comprehensive integration tests for the File Service prove that events are correctly stored in its outbox and relayed to Kafka, even if the business logic initially fails.
- Standardized Prometheus metrics for outbox depth, relay rate, and error count are implemented in the shared library and are active for the File Service's `/metrics` endpoint.
- An `implementation_guide.md` is created, documenting how other services can adopt the new pattern.

## **3. Tasks / Sub-tasks**

-----

### **Story 1: [Foundation] Create the `huleedu-outbox-relay` Shared Library**

- **Description:** Build the core components of the shared library. This forms the foundation for all subsequent service integrations.
- **Tasks:**
  - Create the directory structure `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/`.
  - Implement `protocols.py` with `OutboxRepositoryProtocol` and the `EventTypeMapperProtocol`.
  - Implement `models_db.py` with the generic `EventOutbox` SQLAlchemy model.
  - Implement `repository.py` with the `PostgreSQLOutboxRepository`. This implementation will be generic and work with any `AsyncEngine`.
  - Implement `relay.py` with the `EventRelayWorker`. This worker should be configurable via settings (poll interval, batch size, etc.).
  - Implement `di.py` with a `Dishka OutboxProvider` to provide the repository and worker.
  - Create `alembic/template_migration.py.mako` containing the Alembic script to create the `event_outbox` table.
  - Implement `monitoring.py` to define standard Prometheus metrics (e.g., `outbox_events_pending`, `outbox_events_relayed_total`, `outbox_relay_errors_total`).

-----

### **Story 2: [Pilot] Migrate File Service to Use the Outbox Pattern**

- **Description:** As the first and most critical adopter, the **File Service** must be migrated to use the new `huleedu-outbox-relay` shared library. This will protect its four critical outbound events (`EssayContentProvisionedV1`, `EssayValidationFailedV1`, `BatchFileAddedV1`, `BatchFileRemovedV1`) from being lost if Kafka is unavailable, which currently breaks the entire essay processing pipeline.

- **Implementation Steps:**

    1. **Update Dependencies and DI**

          - In `services/file_service/pyproject.toml`, add `huleedu-service-libs` with the `[outbox]` extra if you define one, or ensure the path resolution is correct in the monorepo.

          - In `services/file_service/di.py`, import and add the `OutboxProvider`.

            ```python
            # services/file_service/di.py

            from dishka import make_async_container
            from huleedu_service_libs.outbox.di import OutboxProvider  # 👈 ADD THIS
            from .implementations import ...

            # In startup_setup.py's initialize_services function
            container = make_async_container(
                CoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
                OutboxProvider(),  # 👈 ADD THIS
            )
            ```

    2. **Create and Run Database Migration**

          - Copy the `template_migration.py.mako` from the shared library into the `services/file_service/` directory (or wherever your Alembic config can find it).
          - Generate a new, dated migration file: `pdm run -p services/file_service migrate-revision "Add event outbox table"`.
          - Apply the migration: `pdm run -p services/file_service migrate-upgrade`.

    3. **Refactor the `DefaultEventPublisher`**

          - Inject `OutboxRepositoryProtocol` into `implementations/event_publisher_impl.py`.

            ```python
            # services/file_service/implementations/event_publisher_impl.py

            from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol

            class DefaultEventPublisher(EventPublisherProtocol):
                def __init__(
                    self,
                    kafka_bus: KafkaPublisherProtocol,
                    settings: Settings,
                    redis_client: AtomicRedisClientProtocol,
                    outbox_repository: OutboxRepositoryProtocol,  # 👈 ADD THIS
                ):
                    self.kafka_bus = kafka_bus
                    self.settings = settings
                    self.redis_client = redis_client
                    self.outbox_repository = outbox_repository  # 👈 ADD THIS
            ```

          - Refactor each `publish_*` method to call `self.outbox_repository.add_event()` instead of `self.kafka_bus.publish()`.

              - **BEFORE:**

                ```python
                await self.kafka_bus.publish(
                    topic=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                    envelope=envelope,
                )
                ```

              - **AFTER:**

                ```python
                topic = self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC

                await self.outbox_repository.add_event(
                    aggregate_id=event_data.file_upload_id,
                    aggregate_type="file_upload",
                    event_type=envelope.event_type,
                    event_data=envelope.model_dump(mode="json"),
                    topic=topic,
                    event_key=event_data.batch_id,
                )
                ```

              - **Note**: Repeat this refactoring for all four `publish_*` methods. The Redis notification logic can remain unchanged.

    4. **Start the Event Relay Worker**

          - In `services/file_service/startup_setup.py`, update `initialize_services` and `shutdown_services` to manage the worker's lifecycle.

            ```python
            # services/file_service/startup_setup.py

            import asyncio
            from huleedu_service_libs.outbox.relay import EventRelayWorker

            event_relay_task: asyncio.Task | None = None

            async def initialize_services(app: Quart, _settings: Settings) -> None:
                global event_relay_task
                # ... existing DI setup ...
                
                async with container() as request_container:
                    event_relay_worker = await request_container.get(EventRelayWorker)
                    event_relay_task = asyncio.create_task(event_relay_worker.start())
                    logger.info("Event Relay Worker for outbox started.")

            async def shutdown_services() -> None:
                if event_relay_task:
                    await event_relay_task.stop() # Assuming a graceful stop method
                    logger.info("Event Relay Worker shutdown.")
            ```

    5. **Update Tests**

          - Update unit tests for `DefaultEventPublisher` to assert that `outbox_repository.add_event` is called.
          - Create a new integration test that verifies the full end-to-end outbox flow for the File Service.

-----

**Story 3: [Documentation] Create Implementation Guide and Operational Playbook**

- **Description:** Document the pattern, the library's usage, and operational procedures for other teams to follow.
- **Tasks:**
  - Write the `implementation_guide.md` in the shared library.
  - Create an initial operational playbook for on-call engineers, covering how to monitor the outbox queue depth and what to do if relaying fails.

-----

**Story 4: [Rollout] Migrate Other Critical Services**

- **Description:** Apply the outbox pattern to the remaining critical services based on the successful pilot.
- **Sub-tasks:**
  - `ARCH-014`: Migrate Batch Orchestrator Service
  - `ARCH-015`: Migrate CJ Assessment Service
  - `ARCH-016`: Migrate Spellchecker Service
  - `ARCH-017`: Migrate Class Management Service

#### **4. Non-Functional Requirements**

- **Testing:** The shared library must have 100% test coverage for its repository and relay logic. Each migrated service must include integration tests verifying the end-to-end outbox flow.
- **Performance:** The overhead of writing to the outbox table must be negligible (\<5ms per transaction). The relay worker must be able to process at least 500 events/second under normal load.
- **Observability:** All key actions (adding to outbox, relaying, error, retry) must be logged with structured data. Prometheus metrics for queue depth, age of the oldest message, and error rates are mandatory.
