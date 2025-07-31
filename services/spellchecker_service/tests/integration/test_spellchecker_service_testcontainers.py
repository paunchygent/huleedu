"""
Integration test for spellchecker service using testcontainers library.

This test uses proper testcontainers (PostgreSQL, Redis, Kafka) to create
an isolated testing environment for the spellchecker service.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List, Tuple
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

logger = create_service_logger("test.spellchecker_testcontainers")


class TestSpellcheckerServiceTestcontainers:
    """Test spellchecker service using testcontainers library."""

    @pytest.fixture(scope="class")
    def real_test_essays(self) -> List[Tuple[str, str]]:
        """Load the same real student essays used in E2E test."""
        essay_dir = Path("test_uploads/real_test_batch")
        if not essay_dir.exists():
            pytest.skip("Real test essays not found")

        essays = []
        # Load essays in same order as E2E test
        for essay_file in sorted(essay_dir.glob("*.txt"))[:30]:  # E2E test uses 25 essays
            content = essay_file.read_text()
            essays.append((essay_file.stem, content))

        if len(essays) < 2:
            pytest.skip("Need at least 2 real essays for test")

        logger.info(f"Loaded {len(essays)} real student essays for testing")
        return essays

    @pytest.fixture(scope="class")
    async def postgres_container(self) -> AsyncGenerator[PostgresContainer, None]:
        """Start PostgreSQL container for testing."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    async def redis_container(self) -> AsyncGenerator[RedisContainer, None]:
        """Start Redis container for testing."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    async def kafka_container(self) -> AsyncGenerator[KafkaContainer, None]:
        """Start Kafka container for testing."""
        container = KafkaContainer()
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    def mock_content_service(
        self, real_test_essays: List[Tuple[str, str]]
    ) -> Generator[str, None, None]:
        """Start a local mock content service that serves test essay content.

        Runs in a separate thread to avoid event loop conflicts.
        """
        import asyncio
        import socket
        import threading

        from aiohttp import web

        # Create content mapping from storage_id to content
        content_map = {}
        for essay_name, content in real_test_essays:
            storage_id = self.create_storage_id_sync(content)
            content_map[storage_id] = content

        # Find an available port
        def find_free_port() -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                s.listen(1)
                port: int = s.getsockname()[1]
            return port

        port = find_free_port()

        async def get_content(request: web.Request) -> web.Response:
            storage_id = request.match_info["storage_id"]
            print(f"🔍 Mock service received request for storage_id: {storage_id}")
            print(f"   Available storage_ids: {list(content_map.keys())}")
            if storage_id in content_map:
                content = content_map[storage_id]
                print(f"   ✅ Returning content: {content[:50]}...")
                return web.Response(text=content, content_type="text/plain", charset="utf-8")
            else:
                print(f"   ❌ Storage ID not found: {storage_id}")
                return web.json_response(
                    {"error": "Content not found", "storage_id": storage_id}, status=404
                )

        async def health(request: web.Request) -> web.Response:
            return web.json_response({"status": "healthy"})

        async def store_content(request: web.Request) -> web.Response:
            """Store corrected content and return storage ID."""
            try:
                content = await request.text()
                storage_id = self.create_storage_id_sync(content)
                # Store the corrected content in the content map
                content_map[storage_id] = content
                print(f"💾 Mock service stored corrected content with storage_id: {storage_id}")
                return web.json_response({"storage_id": storage_id}, status=201)
            except Exception as e:
                print(f"❌ Error storing content: {e}")
                return web.json_response({"error": str(e)}, status=400)

        # Create and start the web application in a separate thread
        def run_mock_server() -> None:
            async def start_server() -> None:
                app = web.Application()
                app.router.add_get("/v1/content/{storage_id}", get_content)
                app.router.add_post("/v1/content", store_content)
                app.router.add_get("/health", health)

                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, "localhost", port)
                await site.start()

                print(f"🌐 Mock content service started at http://localhost:{port}")

                # Keep the server running
                try:
                    while True:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    await runner.cleanup()

            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(start_server())
            except KeyboardInterrupt:
                pass
            finally:
                loop.close()

        # Start server in background thread
        server_thread = threading.Thread(target=run_mock_server, daemon=True)
        server_thread.start()

        # Wait a moment for server to start
        import time

        time.sleep(1)

        service_url = f"http://localhost:{port}"
        logger.info(f"Mock content service started at {service_url}")

        try:
            yield service_url
        finally:
            # Thread will be cleaned up automatically since it's a daemon thread
            pass

    def create_storage_id_sync(self, content: str) -> str:
        """Create a test storage ID for content (sync version)."""
        import hashlib

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"test-storage-{content_hash}"

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
    async def kafka_consumer(
        self, kafka_container: KafkaContainer
    ) -> AsyncGenerator[AIOKafkaConsumer, None]:
        """Create Kafka consumer for results."""
        bootstrap_servers = kafka_container.get_bootstrap_server()
        consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            bootstrap_servers=bootstrap_servers,
            group_id=f"test-{uuid4()}",
            auto_offset_reset="earliest",
        )
        await consumer.start()
        yield consumer
        await consumer.stop()

    @pytest.fixture
    async def spellchecker_service(
        self,
        postgres_container: PostgresContainer,
        redis_container: RedisContainer,
        kafka_container: KafkaContainer,
        mock_content_service: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Start spellchecker service using testcontainers."""
        from dishka import make_async_container
        from sqlalchemy.ext.asyncio import create_async_engine

        from services.spellchecker_service.config import Settings
        from services.spellchecker_service.di import SpellCheckerServiceProvider
        from services.spellchecker_service.kafka_consumer import SpellCheckerKafkaConsumer

        # Get connection details from containers
        postgres_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in postgres_url:
            postgres_url = postgres_url.replace("postgresql://", "postgresql+asyncpg://")

        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
        bootstrap_servers = kafka_container.get_bootstrap_server()

        # Create test settings that override database URL
        class TestSettings(Settings):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                # Store the postgres URL for the property to use
                self._test_postgres_url = str(postgres_url)

            @property
            def database_url(self) -> str:
                """Override database URL to use testcontainer PostgreSQL."""
                return self._test_postgres_url

        settings = TestSettings(
            REDIS_URL=redis_url,
            KAFKA_BOOTSTRAP_SERVERS=bootstrap_servers,
            CONSUMER_GROUP="spellchecker-test",
            CONTENT_SERVICE_URL=f"{mock_content_service}/v1/content",
        )

        print("🔧 Test settings configured:")
        print(f"   Database URL: {settings.database_url}")
        print(f"   Content Service URL: {settings.CONTENT_SERVICE_URL}")
        print(f"   Kafka Bootstrap: {settings.KAFKA_BOOTSTRAP_SERVERS}")
        print(f"   Redis URL: {settings.REDIS_URL}")

        # Create database engine
        engine = create_async_engine(postgres_url, echo=False)

        # Create DI container with test settings and engine
        container = make_async_container(
            SpellCheckerServiceProvider(engine), context={Settings: settings}
        )

        # Initialize the Kafka consumer
        kafka_consumer = await container.get(SpellCheckerKafkaConsumer)

        # Start the consumer in the background
        consumer_task = asyncio.create_task(kafka_consumer.start_consumer())

        try:
            # Wait a moment for the consumer to be ready
            await asyncio.sleep(2)

            yield {
                "settings": settings,
                "postgres_url": postgres_url,
                "redis_url": redis_url,
                "bootstrap_servers": bootstrap_servers,
                "container": container,
                "kafka_consumer": kafka_consumer,
                "engine": engine,
            }

        finally:
            # Stop the consumer
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            await container.close()
            await engine.dispose()

    async def wait_for_result(
        self, consumer: AIOKafkaConsumer, correlation_id: UUID, timeout: float = 10.0
    ) -> Tuple[SpellcheckResultDataV1, float]:
        """Wait for spellcheck result."""
        start_time = time.time()
        print(f"🔍 Waiting for result with correlation_id: {correlation_id}")

        async def get_result() -> Tuple[SpellcheckResultDataV1, float]:
            msg_count = 0
            async for msg in consumer:
                msg_count += 1
                print(f"📨 Received message #{msg_count} on topic {msg.topic}")
                try:
                    envelope = EventEnvelope[SpellcheckResultDataV1].model_validate_json(
                        msg.value.decode()
                    )
                    print(f"   Parsed envelope with correlation_id: {envelope.correlation_id}")
                    if envelope.correlation_id == correlation_id:
                        processing_time = time.time() - start_time
                        print(f"✅ Found matching result in {processing_time:.3f}s")
                        return envelope.data, processing_time
                    else:
                        print("   ⚠ Wrong correlation_id, continuing...")
                except Exception as e:
                    logger.warning(f"Error parsing message: {e}")
                    print(f"   ❌ Failed to parse message: {e}")
                    continue
            # This should never be reached due to async for
            raise RuntimeError("Consumer stopped unexpectedly")

        try:
            return await asyncio.wait_for(get_result(), timeout=timeout)
        except asyncio.TimeoutError:
            processing_time = time.time() - start_time
            print(f"⏰ Timeout after {processing_time:.1f}s waiting for result")
            raise AssertionError(f"Timeout after {processing_time:.1f}s waiting for result")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_spellchecker_performance_with_testcontainers(
        self,
        spellchecker_service: Dict[str, Any],
        real_test_essays: List[Tuple[str, str]],
        kafka_producer: AIOKafkaProducer,
        kafka_consumer: AIOKafkaConsumer,
    ) -> None:
        """Test spellchecker performance using testcontainers."""
        results: List[Dict[str, Any]] = []

        print("\n=== Spellchecker Performance Test (Testcontainers) ===")
        print(f"Testing {len(real_test_essays)} real student essays (same as E2E test)")
        print(f"{'Essay':<30} {'Length':<10} {'Time (s)':<10} {'Corrections':<12} {'Status':<20}")
        print("-" * 85)

        # Test first 2 essays for debugging
        for essay_name, content in real_test_essays[:2]:
            correlation_id = uuid4()

            # Create test storage ID for content (must match mock service)
            storage_id = self.create_storage_id_sync(content)

            # Send spellcheck request with actual content in metadata
            request = EssayLifecycleSpellcheckRequestV1(
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
                text_storage_id=storage_id,
                entity_id=essay_name,
                entity_type="essay",
                parent_id=f"batch-{uuid4()}",
                status=EssayStatus.SPELLCHECKING_IN_PROGRESS,
                system_metadata=SystemProcessingMetadata(
                    entity_id=essay_name,
                    entity_type="essay",
                    parent_id=f"batch-{uuid4()}",
                    timestamp=datetime.now(UTC),
                    started_at=datetime.now(UTC),
                    processing_stage="processing",
                    event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
                ),
                language="en",
            )

            envelope: EventEnvelope[EssayLifecycleSpellcheckRequestV1] = EventEnvelope(
                event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
                source_service="test",
                correlation_id=correlation_id,
                data=request,
                event_timestamp=datetime.now(UTC),
            )

            topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            print(f"\n🚀 Sending message to topic: {topic}")
            print(f"   Storage ID: {storage_id}")
            print(f"   Correlation ID: {correlation_id}")
            print(f"   Content length: {len(content)}")

            await kafka_producer.send(
                topic,
                value=envelope.model_dump_json(),
                key=essay_name.encode(),
            )
            print("✅ Message sent successfully")

            # Wait for result
            try:
                result, processing_time = await self.wait_for_result(
                    kafka_consumer,
                    correlation_id,
                    timeout=5.0,  # Should be fast now
                )

                status = result.status.value if result.status else "Unknown"
                corrections = result.corrections_made or 0

                print(
                    f"{essay_name[:30]:<30} {len(content):<10} {processing_time:<10.3f} "
                    f"{corrections:<12} {status:<20}"
                )

                results.append(
                    {
                        "essay": essay_name,
                        "length": len(content),
                        "time": processing_time,
                        "corrections": corrections,
                        "status": status,
                    }
                )

                # With adaptive distance, should be fast
                assert processing_time < 2.0, f"{essay_name} took {processing_time:.3f}s"

            except AssertionError:
                print(f"{essay_name[:30]:<30} {len(content):<10} TIMEOUT")
                raise

        # Summary
        avg_time = sum(r["time"] for r in results) / len(results)
        max_time = max(r["time"] for r in results)

        print("\n=== Performance Summary ===")
        print(f"Average time: {avg_time:.3f}s")
        print(f"Max time: {max_time:.3f}s")

        # All should be fast with adaptive distance
        assert max_time < 2.0, f"Max time {max_time:.3f}s exceeds 2.0s"
