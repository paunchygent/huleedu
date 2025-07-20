"""
Integration test for spellchecker service with mocked content service.

This test focuses on the spell checking algorithm performance by mocking
the content service and measuring actual processing times.
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Dict, List
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiohttp import web
from common_core.domain_enums import ContentType
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer


class MockContentService:
    """Mock content service that returns predefined essay content."""
    
    # Predefined content for different storage IDs
    CONTENT_MAP = {
        "slow-essay-1": """
        The issue of overconsumption in modern society is a critical problem that affects
        our environment and future generations. Many people are overconsuming resources
        without considering the long-term consequences. This overconsumption pattern
        leads to environmental degradation and resource depletion.
        """,
        
        "slow-essay-2": """
        Children's education about sustainable living is essential. We must teach them
        about the dangers of overconsuming and the importance of conservation. The
        short-term benefits of overconsumption are outweighed by the long-term costs.
        Career-suicide might be what some call advocating for reduced consumption.
        """,
        
        "fast-essay-1": """
        This is a simple essay with some erors. The studnet recieve their homework
        yesterday and they were very happy becouse they got good grades. Their
        teacher was also pleased with their progres this semester.
        """,
        
        "fast-essay-2": """
        The weather today is beutiful. Many peopl are enjoying the sunshine in the
        park. Some are reading books while others are playing gams. It's a perfekt
        day for outdoor activites.
        """,
    }
    
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get("/{storage_id}", self.get_content)
        self.app.router.add_post("/", self.store_content)
        self.runner = None
    
    async def get_content(self, request):
        """Mock GET endpoint for content retrieval."""
        storage_id = request.match_info["storage_id"]
        content = self.CONTENT_MAP.get(storage_id, f"Default content for {storage_id}")
        return web.Response(text=content, status=200)
    
    async def store_content(self, request):
        """Mock POST endpoint for content storage."""
        # Just return a fake storage ID
        new_storage_id = f"stored-{uuid4()}"
        return web.json_response({"storage_id": new_storage_id}, status=201)
    
    async def start(self, port=8001):
        """Start the mock content service."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", port)
        await site.start()
    
    async def stop(self):
        """Stop the mock content service."""
        if self.runner:
            await self.runner.cleanup()


class TestSpellcheckerWithMockContent:
    """Test spellchecker service performance with mocked dependencies."""
    
    @pytest.fixture
    async def kafka_container(self):
        """Create and start a Kafka container."""
        kafka = KafkaContainer()
        kafka.start()
        yield kafka
        kafka.stop()
    
    @pytest.fixture
    async def redis_container(self):
        """Create and start a Redis container."""
        redis = RedisContainer()
        redis.start()
        yield redis
        redis.stop()
    
    @pytest.fixture
    async def mock_content_service(self):
        """Run mock content service."""
        service = MockContentService()
        await service.start()
        yield service
        await service.stop()
    
    @pytest.fixture
    async def kafka_producer(self, kafka_container):
        """Create Kafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_container.get_bootstrap_server()
        )
        await producer.start()
        yield producer
        await producer.stop()
    
    @pytest.fixture
    async def kafka_consumer(self, kafka_container):
        """Create Kafka consumer for results."""
        consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            group_id=f"test-group-{uuid4()}",
            auto_offset_reset='earliest'
        )
        await consumer.start()
        yield consumer
        await consumer.stop()
    
    async def send_spellcheck_request(
        self,
        producer: AIOKafkaProducer,
        storage_id: str,
        essay_id: str,
        correlation_id: UUID
    ):
        """Send a spellcheck request with the given storage ID."""
        request = EssayLifecycleSpellcheckRequestV1(
            text_storage_id=storage_id,
            entity_ref=EntityReference(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=f"batch-{uuid4()}"
            ),
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=essay_id, entity_type="essay"),
                timestamp=datetime.now(UTC),
                started_at=datetime.now(UTC),
                processing_stage=ProcessingStage.SPELLCHECK,
                event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            ),
            language="en",
        )
        
        envelope = EventEnvelope(
            event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            source_service="test-service",
            correlation_id=correlation_id,
            data=request,
        )
        
        await producer.send(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
            value=envelope.model_dump_json().encode(),
            key=essay_id.encode()
        )
    
    async def wait_for_result(
        self,
        consumer: AIOKafkaConsumer,
        correlation_id: UUID,
        timeout: float = 30.0
    ) -> tuple[SpellcheckResultDataV1, float]:
        """Wait for result and return data with processing time."""
        start_time = time.time()
        
        async def consume():
            async for msg in consumer:
                try:
                    envelope = EventEnvelope[SpellcheckResultDataV1].model_validate_json(
                        msg.value.decode()
                    )
                    if envelope.correlation_id == correlation_id:
                        processing_time = time.time() - start_time
                        return envelope.data, processing_time
                except Exception as e:
                    print(f"Error parsing message: {e}")
                    continue
        
        try:
            return await asyncio.wait_for(consume(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Timeout after {timeout}s waiting for correlation_id {correlation_id}")
    
    @pytest.mark.asyncio
    async def test_performance_comparison(
        self,
        kafka_producer,
        kafka_consumer,
        mock_content_service
    ):
        """Compare performance between fast and slow essays."""
        test_cases = [
            ("slow-essay-1", "Slow Essay 1 (overconsumption)"),
            ("slow-essay-2", "Slow Essay 2 (children's, short-term)"),
            ("fast-essay-1", "Fast Essay 1 (simple errors)"),
            ("fast-essay-2", "Fast Essay 2 (simple errors)"),
        ]
        
        results = []
        
        print("\n=== Spellchecker Performance Test ===")
        print(f"{'Storage ID':<15} {'Description':<35} {'Time (s)':<10} {'Status':<20}")
        print("-" * 85)
        
        for storage_id, description in test_cases:
            correlation_id = uuid4()
            essay_id = f"essay-{storage_id}"
            
            # Send request
            await self.send_spellcheck_request(
                kafka_producer,
                storage_id,
                essay_id,
                correlation_id
            )
            
            # Wait for result
            try:
                result, processing_time = await self.wait_for_result(
                    kafka_consumer,
                    correlation_id,
                    timeout=15.0
                )
                status = result.status.value if result.status else "Unknown"
                corrections = result.corrections_made or 0
                
                print(f"{storage_id:<15} {description:<35} {processing_time:<10.3f} {status:<20}")
                
                results.append({
                    "storage_id": storage_id,
                    "time": processing_time,
                    "corrections": corrections,
                    "is_slow": storage_id.startswith("slow"),
                })
                
            except AssertionError as e:
                print(f"{storage_id:<15} {description:<35} TIMEOUT      FAILED")
                results.append({
                    "storage_id": storage_id,
                    "time": 15.0,
                    "corrections": 0,
                    "is_slow": storage_id.startswith("slow"),
                })
        
        # Analyze results
        slow_times = [r["time"] for r in results if r["is_slow"]]
        fast_times = [r["time"] for r in results if not r["is_slow"]]
        
        if slow_times and fast_times:
            avg_slow = sum(slow_times) / len(slow_times)
            avg_fast = sum(fast_times) / len(fast_times)
            
            print(f"\n=== Performance Summary ===")
            print(f"Average time for slow essays: {avg_slow:.3f}s")
            print(f"Average time for fast essays: {avg_fast:.3f}s")
            print(f"Slowdown factor: {avg_slow / avg_fast:.1f}x")
            
            # Verify that slow essays are actually slower
            assert avg_slow > avg_fast * 2, \
                f"Expected slow essays to be at least 2x slower, but ratio is {avg_slow/avg_fast:.1f}x"
    
    @pytest.mark.asyncio
    async def test_specific_problematic_words(
        self,
        kafka_producer,
        kafka_consumer,
        mock_content_service
    ):
        """Test specific words that cause performance issues."""
        # Add test content with specific problematic words
        test_id = "specific-test"
        MockContentService.CONTENT_MAP[test_id] = """
        Testing specific problematic words:
        - overconsumption (compound word, 15 chars)
        - children's (contraction with apostrophe)
        - short-term (hyphenated compound)
        - career-suicide (hyphenated, 14 chars)
        
        These words cause PySpellChecker to take excessive time.
        """
        
        correlation_id = uuid4()
        essay_id = f"essay-{test_id}"
        
        print("\n=== Testing Specific Problematic Words ===")
        
        await self.send_spellcheck_request(
            kafka_producer,
            test_id,
            essay_id,
            correlation_id
        )
        
        result, processing_time = await self.wait_for_result(
            kafka_consumer,
            correlation_id,
            timeout=20.0
        )
        
        print(f"Processing time: {processing_time:.3f}s")
        print(f"Corrections made: {result.corrections_made}")
        
        # This should be slow with current implementation
        assert processing_time > 2.0, \
            f"Expected slow processing (>2s) for problematic words, but got {processing_time:.3f}s"


if __name__ == "__main__":
    # Run with: pdm run pytest -v -s <this_file>
    pytest.main([__file__, "-v", "-s"])