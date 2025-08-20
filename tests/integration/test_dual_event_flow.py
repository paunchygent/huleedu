"""
Real integration test for dual event pattern implementation in spellcheck flow.

This test uses testcontainers to create real PostgreSQL, Kafka, and Redis infrastructure
to validate the complete dual event pattern where spellchecker publishes both:
1. Thin events (SpellcheckPhaseCompletedV1) for state management
2. Rich events (SpellcheckResultV1) for business data aggregation

CRITICAL: Tests the bug fix for commanded_phases metadata preservation.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import pytest
from aiohttp import ClientSession
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckPhaseCompletedV1,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.config import Settings as ELSSettings
from services.essay_lifecycle_service.di import (
    BatchCoordinationProvider,
    CommandHandlerProvider,
    CoreInfrastructureProvider,
    ServiceClientsProvider,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.models_db import Base
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol, ServiceResultHandler
from services.spellchecker_service.config import Settings as SpellcheckerSettings
from services.spellchecker_service.di import SpellCheckerServiceProvider
from services.spellchecker_service.kafka_consumer import SpellCheckerKafkaConsumer

logger = create_service_logger("test_dual_event_flow_integration")


class TestDualEventPatternIntegration:
    """REAL integration tests using testcontainers for dual event pattern."""

    @pytest.fixture(scope="class")
    async def postgres_container(self) -> AsyncGenerator[PostgresContainer, None]:
        """Start PostgreSQL for both spellchecker and ELS."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    async def redis_container(self) -> AsyncGenerator[RedisContainer, None]:
        """Start Redis container for idempotency."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    async def kafka_container(self) -> AsyncGenerator[KafkaContainer, None]:
        """Start Kafka with required topics."""
        container = KafkaContainer()
        container.start()

        # Create required topics
        bootstrap_servers = container.get_bootstrap_server()
        admin_client = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
        await admin_client.start()

        topics_to_create = [
            NewTopic(
                name=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
                num_partitions=1,
                replication_factor=1,
            ),
            NewTopic(
                name=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
                num_partitions=1,
                replication_factor=1,
            ),
            NewTopic(
                name=topic_name(ProcessingEvent.SPELLCHECK_RESULTS),
                num_partitions=1,
                replication_factor=1,
            ),
        ]

        try:
            await admin_client.create_topics(topics_to_create)
            logger.info("Created Kafka topics for dual event pattern test")
        except Exception as e:
            logger.warning(f"Topic creation failed (may already exist): {e}")
        finally:
            await admin_client.close()

        yield container
        container.stop()

    @pytest.fixture
    async def els_database_engine(
        self, postgres_container: PostgresContainer
    ) -> AsyncGenerator[Any, None]:
        """Create ELS database engine with schema."""
        postgres_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in postgres_url:
            postgres_url = postgres_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(postgres_url, echo=False)

        # Create ELS schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Created ELS database schema")

        yield engine
        await engine.dispose()

    @pytest.fixture
    async def mock_content_service(self) -> AsyncGenerator[str, None]:
        """Simple mock content service that returns test content."""
        import socket
        import threading

        from aiohttp import web

        # Find available port
        def find_free_port() -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                s.listen(1)
                port_value: int = s.getsockname()[1]
                return port_value

        port = find_free_port()
        test_content = "This is a test essay with some misspellings like recieve and occurance."

        async def get_content(request: web.Request) -> web.Response:
            return web.Response(text=test_content, content_type="text/plain", charset="utf-8")

        async def store_content(request: web.Request) -> web.Response:
            await request.text()
            storage_id = f"corrected-{uuid4()}"
            return web.json_response({"storage_id": storage_id}, status=201)

        def run_server() -> None:
            async def start_server() -> None:
                app = web.Application()
                app.router.add_get("/v1/content/{storage_id}", get_content)
                app.router.add_post("/v1/content", store_content)

                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, "localhost", port)
                await site.start()

                try:
                    while True:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    await runner.cleanup()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(start_server())
            except KeyboardInterrupt:
                pass
            finally:
                loop.close()

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(1)  # Let server start

        yield f"http://localhost:{port}"

    @pytest.fixture
    async def kafka_producer(
        self, kafka_container: KafkaContainer
    ) -> AsyncGenerator[AIOKafkaProducer, None]:
        """Create Kafka producer."""
        bootstrap_servers = kafka_container.get_bootstrap_server()
        producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: v.encode() if isinstance(v, str) else json.dumps(v).encode(),
        )
        await producer.start()
        yield producer
        await producer.stop()

    @pytest.fixture
    async def dual_event_consumers(
        self, kafka_container: KafkaContainer
    ) -> AsyncGenerator[Dict[str, AIOKafkaConsumer], None]:
        """Create consumers for both thin and rich events."""
        bootstrap_servers = kafka_container.get_bootstrap_server()

        thin_consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            bootstrap_servers=bootstrap_servers,
            group_id=f"test-thin-{uuid4()}",
            auto_offset_reset="earliest",
        )

        rich_consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.SPELLCHECK_RESULTS),
            bootstrap_servers=bootstrap_servers,
            group_id=f"test-rich-{uuid4()}",
            auto_offset_reset="earliest",
        )

        await thin_consumer.start()
        await rich_consumer.start()

        yield {
            "thin": thin_consumer,
            "rich": rich_consumer,
        }

        await thin_consumer.stop()
        await rich_consumer.stop()

    @pytest.fixture
    async def integrated_services(
        self,
        postgres_container: PostgresContainer,
        redis_container: RedisContainer,
        kafka_container: KafkaContainer,
        mock_content_service: str,
        els_database_engine: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Setup integrated services with real containers."""
        postgres_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in postgres_url:
            postgres_url = postgres_url.replace("postgresql://", "postgresql+asyncpg://")

        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
        bootstrap_servers = kafka_container.get_bootstrap_server()

        # Create ELS settings
        class TestELSSettings(ELSSettings):
            _test_postgres_url: str
            # Use real repository in tests
            USE_MOCK_REPOSITORY: bool = False

            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self._test_postgres_url = postgres_url

            @property
            def DATABASE_URL(self) -> str:  # noqa: N802 - matches Settings property name
                return self._test_postgres_url

        els_settings = TestELSSettings(
            REDIS_URL=redis_url,
            KAFKA_BOOTSTRAP_SERVERS=bootstrap_servers,
            CONSUMER_GROUP="els-test",
        )

        # Create Spellchecker settings
        class TestSpellcheckerSettings(SpellcheckerSettings):
            _test_postgres_url: str

            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self._test_postgres_url = postgres_url

            @property
            def database_url(self) -> str:
                return self._test_postgres_url

        spellchecker_settings = TestSpellcheckerSettings(
            REDIS_URL=redis_url,
            KAFKA_BOOTSTRAP_SERVERS=bootstrap_servers,
            CONSUMER_GROUP="spellchecker-test",
            CONTENT_SERVICE_URL=f"{mock_content_service}/v1/content",
        )

        # Create DI containers
        els_engine = create_async_engine(postgres_url, echo=False)
        spellchecker_engine = create_async_engine(postgres_url, echo=False)

        # Force ELS to use the test engine and a real Postgres repo via context overrides
        postgres_repo = PostgreSQLEssayRepository(els_settings, database_metrics=None)

        els_container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceClientsProvider(),
            CommandHandlerProvider(),
            BatchCoordinationProvider(),
            OutboxProvider(),
            context={
                AsyncEngine: els_engine,  # Ensure session_factory uses test DB engine
                EssayRepositoryProtocol: postgres_repo,  # Ensure handler uses real repo
                ELSSettings: els_settings,
            },
        )

        spellchecker_container = make_async_container(
            SpellCheckerServiceProvider(spellchecker_engine),
            context={SpellcheckerSettings: spellchecker_settings},
        )

        # Get services
        spellchecker_consumer = await spellchecker_container.get(SpellCheckerKafkaConsumer)
        spellchecker_relay_worker = await spellchecker_container.get(EventRelayWorker)
        els_repository = await els_container.get(EssayRepositoryProtocol)
        els_service_result_handler = await els_container.get(ServiceResultHandler)

        # Track resources to close explicitly to avoid unclosed warnings
        els_kafka_bus = None
        sp_kafka_bus = None
        els_http_session = None
        sp_http_session = None

        try:
            from huleedu_service_libs.protocols import KafkaPublisherProtocol

            els_kafka_bus = await els_container.get(KafkaPublisherProtocol)
            sp_kafka_bus = await spellchecker_container.get(KafkaPublisherProtocol)
        except Exception:
            pass

        try:
            els_http_session = await els_container.get(ClientSession)
            sp_http_session = await spellchecker_container.get(ClientSession)
        except Exception:
            pass

        # Start spellchecker consumer and relay worker
        consumer_task = asyncio.create_task(spellchecker_consumer.start_consumer())
        await spellchecker_relay_worker.start()  # Start relay worker for outbox pattern

        # Create and start a simple ELS consumer for thin events
        els_consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            bootstrap_servers=bootstrap_servers,
            group_id="els-test",
            auto_offset_reset="earliest",
        )
        await els_consumer.start()

        async def els_consumer_loop():
            """Simple consumer loop for ELS to process thin events."""
            from common_core.status_enums import ProcessingStatus as PStatus

            async for msg in els_consumer:
                try:
                    # Deserialize envelope and event
                    envelope = EventEnvelope.model_validate_json(msg.value)
                    event = SpellcheckPhaseCompletedV1.model_validate(envelope.data)

                    # Map thin event ProcessingStatus to ELS EssayStatus
                    mapped_status = (
                        EssayStatus.SPELLCHECKED_SUCCESS
                        if event.status == PStatus.COMPLETED
                        else EssayStatus.SPELLCHECK_FAILED
                    )

                    # Call the handler that preserves metadata
                    await els_service_result_handler.handle_spellcheck_phase_completed(
                        essay_id=event.entity_id,
                        batch_id=event.batch_id,
                        status=mapped_status,
                        corrected_text_storage_id=event.corrected_text_storage_id,
                        error_code=event.error_code,
                        correlation_id=envelope.correlation_id,
                    )
                    logger.info("ELS processed thin event", extra={"essay_id": event.entity_id})
                except Exception as e:
                    logger.error(f"Error processing thin event in ELS: {e}")

        els_consumer_task = asyncio.create_task(els_consumer_loop())

        try:
            await asyncio.sleep(2)  # Let services start

            yield {
                "els_container": els_container,
                "spellchecker_container": spellchecker_container,
                "els_repository": els_repository,
                "els_engine": els_engine,
                "spellchecker_consumer": spellchecker_consumer,
                "els_settings": els_settings,
                "spellchecker_settings": spellchecker_settings,
            }

        finally:
            consumer_task.cancel()
            els_consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            try:
                await els_consumer_task
            except asyncio.CancelledError:
                pass
            await els_consumer.stop()
            await spellchecker_relay_worker.stop()  # Stop relay worker
            # Stop Kafka buses and HTTP sessions explicitly to prevent resource warnings
            try:
                if els_kafka_bus is not None:
                    await els_kafka_bus.stop()
            except Exception:
                pass
            try:
                if sp_kafka_bus is not None:
                    await sp_kafka_bus.stop()
            except Exception:
                pass
            try:
                if els_http_session is not None:
                    await els_http_session.close()
            except Exception:
                pass
            try:
                if sp_http_session is not None:
                    await sp_http_session.close()
            except Exception:
                pass

            await els_container.close()
            await spellchecker_container.close()
            await els_engine.dispose()
            await spellchecker_engine.dispose()

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_metadata_preservation_bug_fix(
        self,
        integrated_services: Dict[str, Any],
        kafka_producer: AIOKafkaProducer,
        dual_event_consumers: Dict[str, AIOKafkaConsumer],
    ) -> None:
        """
        CRITICAL TEST: Verify the bug fix preserves commanded_phases metadata.

        This test:
        1. Creates an essay in the database with initial commanded_phases metadata
        2. Publishes a SpellcheckRequest to Kafka
        3. Waits for the spellchecker service to process and publish dual events
        4. Queries the database to verify commanded_phases was preserved and spellcheck added
        """
        essay_id = f"essay-{uuid4()}"
        batch_id = f"batch-{uuid4()}"
        correlation_id = uuid4()
        original_storage_id = f"original-{uuid4()}"

        logger.info(
            "Starting metadata preservation test",
            extra={
                "essay_id": essay_id,
                "batch_id": batch_id,
                "correlation_id": str(correlation_id),
            },
        )

        # STEP 1: Create essay with initial metadata (simulating upload/validation phases)
        initial_metadata = {
            "commanded_phases": ["upload", "validation"],  # Pre-existing phases
            "current_phase": "validation",
            "phase_outcome_status": "VALIDATION_SUCCESS",
        }

        integrated_services["els_repository"]
        engine = integrated_services["els_engine"]

        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            # First insert batch tracker (required for foreign key constraint)
            await session.execute(
                text("""
                    INSERT INTO batch_essay_trackers (
                        batch_id, expected_essay_ids, available_slots, expected_count,
                        course_code, essay_instructions, user_id, correlation_id,
                        timeout_seconds, created_at, updated_at
                    ) VALUES (
                        :batch_id, :expected_ids, :available_slots, :expected_count,
                        :course_code, :essay_instructions, :user_id, :correlation_id,
                        :timeout_seconds, NOW(), NOW()
                    )
                """),
                {
                    "batch_id": batch_id,
                    "expected_ids": json.dumps([essay_id]),
                    "available_slots": json.dumps([]),
                    "expected_count": 1,
                    "course_code": "ENG5",
                    "essay_instructions": "Test essay for integration testing",
                    "user_id": "test-user",
                    "correlation_id": str(correlation_id),
                    "timeout_seconds": 86400,  # 24 hours default
                },
            )

            # Insert essay state with initial metadata
            await session.execute(
                text("""
                    INSERT INTO essay_states (
                        essay_id, batch_id, current_status, processing_metadata,
                        timeline, storage_references, text_storage_id,
                        version, created_at, updated_at
                    ) VALUES (
                        :essay_id, :batch_id, :status, :metadata,
                        :timeline, :storage_refs, :text_storage_id,
                        1, NOW(), NOW()
                    )
                """),
                {
                    "essay_id": essay_id,
                    "batch_id": batch_id,
                    "status": EssayStatus.SPELLCHECKING_IN_PROGRESS.value,
                    "metadata": json.dumps(initial_metadata),
                    "timeline": json.dumps({}),
                    "storage_refs": json.dumps({"original_essay": original_storage_id}),
                    "text_storage_id": original_storage_id,
                },
            )
            await session.commit()

        logger.info(
            "Created essay with initial metadata", extra={"initial_metadata": initial_metadata}
        )

        # STEP 2: Publish spellcheck request
        request = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            text_storage_id=original_storage_id,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECKING_IN_PROGRESS,
            system_metadata=SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=batch_id,
                timestamp=datetime.now(UTC),
                started_at=datetime.now(UTC),
                processing_stage="processing",
                event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            ),
            language="en",
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            source_service="test",
            correlation_id=correlation_id,
            data=request,
            event_timestamp=datetime.now(UTC),
        )

        topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
        await kafka_producer.send(topic, value=envelope.model_dump_json())

        logger.info("Published spellcheck request", extra={"topic": topic})

        # STEP 3: Wait for dual events
        thin_event_received = False
        rich_event_received = False
        timeout_start = time.time()
        timeout_seconds = 10.0

        while (not thin_event_received or not rich_event_received) and (
            time.time() - timeout_start < timeout_seconds
        ):
            # Check for thin event
            if not thin_event_received:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["thin"].getone(), timeout=1.0)
                    envelope_data = json.loads(msg.value.decode())
                    if envelope_data.get("correlation_id") == str(correlation_id):
                        thin_event_received = True
                        logger.info("Received thin event", extra={"event": envelope_data})
                except asyncio.TimeoutError:
                    pass

            # Check for rich event
            if not rich_event_received:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["rich"].getone(), timeout=1.0)
                    envelope_data = json.loads(msg.value.decode())
                    if envelope_data.get("correlation_id") == str(correlation_id):
                        rich_event_received = True
                        logger.info("Received rich event", extra={"event": envelope_data})
                except asyncio.TimeoutError:
                    pass

        assert thin_event_received, "Thin event not received within timeout"
        assert rich_event_received, "Rich event not received within timeout"

        # STEP 4: Query database to verify metadata preservation
        # Poll the database until the ELS consumer has processed the event
        metadata_updated = False
        poll_start = time.time()
        poll_timeout = 5.0  # Give ELS consumer time to process
        final_metadata = None

        while not metadata_updated and (time.time() - poll_start < poll_timeout):
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT processing_metadata FROM essay_states WHERE essay_id = :essay_id"),
                    {"essay_id": essay_id},
                )
                row = result.fetchone()

            if row is not None:
                final_metadata = row[0]
                # Check if metadata has been updated with spellcheck phase
                if (
                    "commanded_phases" in final_metadata
                    and "spellcheck" in final_metadata["commanded_phases"]
                ):
                    metadata_updated = True
                    logger.info(
                        "Metadata updated by ELS consumer", extra={"final_metadata": final_metadata}
                    )
                    break

            await asyncio.sleep(0.1)  # Small polling interval

        assert metadata_updated, f"ELS consumer did not update metadata within {poll_timeout}s"
        assert final_metadata is not None, f"Essay {essay_id} not found after processing"

        # CRITICAL ASSERTIONS: Verify bug fix worked
        assert "commanded_phases" in final_metadata, "commanded_phases missing from final metadata"

        final_commanded_phases = final_metadata["commanded_phases"]
        assert "upload" in final_commanded_phases, "Original 'upload' phase lost"
        assert "validation" in final_commanded_phases, "Original 'validation' phase lost"
        assert "spellcheck" in final_commanded_phases, "New 'spellcheck' phase not added"

        # Verify order and completeness
        expected_phases = ["upload", "validation", "spellcheck"]
        assert final_commanded_phases == expected_phases, (
            f"Expected {expected_phases}, got {final_commanded_phases}"
        )

        # Verify other metadata updates
        assert final_metadata["current_phase"] == "spellcheck"
        assert final_metadata["phase_outcome_status"] in [
            EssayStatus.SPELLCHECKED_SUCCESS.value,
            EssayStatus.SPELLCHECK_FAILED.value,
        ]

        logger.info("BUG FIX VALIDATED: commanded_phases metadata preserved correctly")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dual_event_size_comparison(
        self,
        integrated_services: Dict[str, Any],
        kafka_producer: AIOKafkaProducer,
        dual_event_consumers: Dict[str, AIOKafkaConsumer],
    ) -> None:
        """
        Test that validates actual event size differences between thin and rich events.
        This measures real serialized event sizes from Kafka.
        """
        essay_id = f"essay-{uuid4()}"
        batch_id = f"batch-{uuid4()}"
        correlation_id = uuid4()
        original_storage_id = f"original-{uuid4()}"

        # Setup essay in database (minimal setup for this test)
        integrated_services["els_repository"]
        engine = integrated_services["els_engine"]

        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            # First insert batch tracker (required for foreign key constraint)
            await session.execute(
                text("""
                    INSERT INTO batch_essay_trackers (
                        batch_id, expected_essay_ids, available_slots, expected_count,
                        course_code, essay_instructions, user_id, correlation_id,
                        timeout_seconds, created_at, updated_at
                    ) VALUES (
                        :batch_id, :expected_ids, :available_slots, :expected_count,
                        :course_code, :essay_instructions, :user_id, :correlation_id,
                        :timeout_seconds, NOW(), NOW()
                    )
                """),
                {
                    "batch_id": batch_id,
                    "expected_ids": json.dumps([essay_id]),
                    "available_slots": json.dumps([]),
                    "expected_count": 1,
                    "course_code": "ENG5",
                    "essay_instructions": "Test essay for integration testing",
                    "user_id": "test-user",
                    "correlation_id": str(correlation_id),
                    "timeout_seconds": 86400,  # 24 hours default
                },
            )

            await session.execute(
                text("""
                    INSERT INTO essay_states (
                        essay_id, batch_id, current_status, processing_metadata,
                        timeline, storage_references, text_storage_id,
                        version, created_at, updated_at
                    ) VALUES (
                        :essay_id, :batch_id, :status, :metadata,
                        :timeline, :storage_refs, :text_storage_id,
                        1, NOW(), NOW()
                    )
                """),
                {
                    "essay_id": essay_id,
                    "batch_id": batch_id,
                    "status": EssayStatus.SPELLCHECKING_IN_PROGRESS.value,
                    "metadata": json.dumps({"commanded_phases": ["upload"]}),
                    "timeline": json.dumps({}),
                    "storage_refs": json.dumps({"original_essay": original_storage_id}),
                    "text_storage_id": original_storage_id,
                },
            )
            await session.commit()

        # Publish spellcheck request and capture events
        request = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            text_storage_id=original_storage_id,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECKING_IN_PROGRESS,
            system_metadata=SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=batch_id,
                timestamp=datetime.now(UTC),
                started_at=datetime.now(UTC),
                processing_stage="processing",
                event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            ),
            language="en",
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            source_service="test",
            correlation_id=correlation_id,
            data=request,
            event_timestamp=datetime.now(UTC),
        )

        await kafka_producer.send(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
            value=envelope.model_dump_json(),
        )

        # Capture both events and measure sizes
        thin_event_size = None
        rich_event_size = None
        timeout_start = time.time()

        while (thin_event_size is None or rich_event_size is None) and (
            time.time() - timeout_start < 10.0
        ):
            # Check thin event
            if thin_event_size is None:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["thin"].getone(), timeout=1.0)
                    if json.loads(msg.value.decode()).get("correlation_id") == str(correlation_id):
                        thin_event_size = len(msg.value)
                        logger.info(f"Captured thin event: {thin_event_size} bytes")
                except asyncio.TimeoutError:
                    pass

            # Check rich event
            if rich_event_size is None:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["rich"].getone(), timeout=1.0)
                    if json.loads(msg.value.decode()).get("correlation_id") == str(correlation_id):
                        rich_event_size = len(msg.value)
                        logger.info(f"Captured rich event: {rich_event_size} bytes")
                except asyncio.TimeoutError:
                    pass

        assert thin_event_size is not None, "Failed to capture thin event"
        assert rich_event_size is not None, "Failed to capture rich event"

        # Calculate size reduction
        size_reduction_percent = ((rich_event_size - thin_event_size) / rich_event_size) * 100

        logger.info(
            f"Event size comparison: thin={thin_event_size} bytes, "
            f"rich={rich_event_size} bytes, reduction={size_reduction_percent:.1f}%"
        )

        # Verify size difference (realistic expectations)
        assert thin_event_size < rich_event_size, "Thin event should be smaller than rich event"
        assert size_reduction_percent >= 30, (
            f"Size reduction is {size_reduction_percent:.1f}%, expected at least 30%"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dual_event_topic_separation(
        self,
        integrated_services: Dict[str, Any],
        kafka_producer: AIOKafkaProducer,
        dual_event_consumers: Dict[str, AIOKafkaConsumer],
    ) -> None:
        """
        Test that dual events are published to different topics as designed.
        This validates the architectural separation for different service consumption.
        """
        essay_id = f"essay-{uuid4()}"
        batch_id = f"batch-{uuid4()}"
        correlation_id = uuid4()
        original_storage_id = f"original-{uuid4()}"

        # Setup and trigger processing (abbreviated setup)
        engine = integrated_services["els_engine"]
        async with engine.begin() as conn:
            session = AsyncSession(conn, expire_on_commit=False)

            # First insert batch tracker (required for foreign key constraint)
            await session.execute(
                text("""
                    INSERT INTO batch_essay_trackers (
                        batch_id, expected_essay_ids, available_slots, expected_count,
                        course_code, essay_instructions, user_id, correlation_id,
                        timeout_seconds, created_at, updated_at
                    ) VALUES (
                        :batch_id, :expected_ids, :available_slots, :expected_count,
                        :course_code, :essay_instructions, :user_id, :correlation_id,
                        :timeout_seconds, NOW(), NOW()
                    )
                """),
                {
                    "batch_id": batch_id,
                    "expected_ids": json.dumps([essay_id]),
                    "available_slots": json.dumps([]),
                    "expected_count": 1,
                    "course_code": "TEST101",
                    "essay_instructions": "Test essay for integration testing",
                    "user_id": "test-user",
                    "correlation_id": str(correlation_id),
                    "timeout_seconds": 86400,  # 24 hours default
                },
            )

            await session.execute(
                text("""
                    INSERT INTO essay_states (
                        essay_id, batch_id, current_status, processing_metadata,
                        timeline, storage_references, text_storage_id,
                        version, created_at, updated_at
                    ) VALUES (
                        :essay_id, :batch_id, :status, :metadata,
                        :timeline, :storage_refs, :text_storage_id,
                        1, NOW(), NOW()
                    )
                """),
                {
                    "essay_id": essay_id,
                    "batch_id": batch_id,
                    "status": EssayStatus.SPELLCHECKING_IN_PROGRESS.value,
                    "metadata": json.dumps({"commanded_phases": ["upload"]}),
                    "timeline": json.dumps({}),
                    "storage_refs": json.dumps({"original_text": original_storage_id}),
                    "text_storage_id": original_storage_id,
                },
            )
            await session.commit()

        # Publish request
        request = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            text_storage_id=original_storage_id,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECKING_IN_PROGRESS,
            system_metadata=SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=batch_id,
                timestamp=datetime.now(UTC),
                started_at=datetime.now(UTC),
                processing_stage="processing",
                event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            ),
            language="en",
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            source_service="test",
            correlation_id=correlation_id,
            data=request,
            event_timestamp=datetime.now(UTC),
        )

        await kafka_producer.send(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
            value=envelope.model_dump_json(),
        )

        # Verify events arrive on correct topics
        thin_topic_confirmed = False
        rich_topic_confirmed = False
        timeout_start = time.time()

        while (not thin_topic_confirmed or not rich_topic_confirmed) and (
            time.time() - timeout_start < 10.0
        ):
            # Check thin event topic
            if not thin_topic_confirmed:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["thin"].getone(), timeout=1.0)
                    if json.loads(msg.value.decode()).get("correlation_id") == str(correlation_id):
                        assert msg.topic == topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
                        thin_topic_confirmed = True
                        logger.info(f"Thin event confirmed on topic: {msg.topic}")
                except asyncio.TimeoutError:
                    pass

            # Check rich event topic
            if not rich_topic_confirmed:
                try:
                    msg = await asyncio.wait_for(dual_event_consumers["rich"].getone(), timeout=1.0)
                    if json.loads(msg.value.decode()).get("correlation_id") == str(correlation_id):
                        assert msg.topic == topic_name(ProcessingEvent.SPELLCHECK_RESULTS)
                        rich_topic_confirmed = True
                        logger.info(f"Rich event confirmed on topic: {msg.topic}")
                except asyncio.TimeoutError:
                    pass

        assert thin_topic_confirmed, "Thin event not received on expected topic"
        assert rich_topic_confirmed, "Rich event not received on expected topic"

        logger.info("ARCHITECTURAL VALIDATION: Dual events published to separate topics correctly")
