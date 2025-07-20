"""
Integration test for spellchecker service performance using testcontainers.

This test runs the actual spellchecker service in a container and sends
real essay content through Kafka to reproduce the performance bottleneck.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core.domain_enums import ContentType
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from testcontainers.compose import DockerCompose
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


class TestSpellcheckerServicePerformance:
    """Test spellchecker service performance with real essays using testcontainers."""
    
    # Real essay content that causes performance issues
    PROBLEMATIC_ESSAY = """
    The issue of overconsumption in modern society is a critical problem that affects
    our environment and future generations. Many people are overconsuming resources
    without considering the long-term consequences. This overconsumption pattern
    leads to environmental degradation and resource depletion.
    
    Children's education about sustainable living is essential. We must teach them
    about the dangers of overconsuming and the importance of conservation. The
    short-term benefits of overconsumption are outweighed by the long-term costs.
    
    Career-suicide might be what some call advocating for reduced consumption, but
    it's a necessary stance. We cannot continue overconsuming at current rates.
    The overconsumption of resources is unsustainable, and overconsuming individuals
    must change their habits.
    """
    
    @pytest.fixture
    async def kafka_container(self):
        """Create and start a Kafka container."""
        with KafkaContainer() as kafka:
            yield kafka
    
    @pytest.fixture
    async def redis_container(self):
        """Create and start a Redis container."""
        with RedisContainer() as redis:
            yield redis
    
    @pytest.fixture
    async def postgres_container(self):
        """Create and start a PostgreSQL container."""
        with PostgresContainer("postgres:15") as postgres:
            yield postgres
    
    @pytest.fixture
    async def spellchecker_service(self, kafka_container, redis_container):
        """Run spellchecker service with testcontainers."""
        # Create a minimal docker-compose override for the service
        compose_content = f"""
version: '3.8'
services:
  spellchecker_service:
    build:
      context: ../../../../
      dockerfile: services/spellchecker_service/Dockerfile
    environment:
      - KAFKA_BOOTSTRAP_SERVERS={kafka_container.get_bootstrap_server()}
      - REDIS_URL=redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}
      - SPELLCHECKER_SERVICE_PORT=8002
      - SPELLCHECKER_ENABLED=true
      - ENABLE_L2_CORRECTIONS=true
      - LOG_LEVEL=DEBUG
    depends_on:
      - kafka
      - redis
"""
        
        # Write temporary compose file
        compose_file = Path("/tmp/test_spellchecker_compose.yml")
        compose_file.write_text(compose_content)
        
        with DockerCompose(
            str(compose_file.parent),
            compose_file_name=compose_file.name,
            pull=False,
            build=True
        ) as compose:
            # Wait for service to be ready
            await asyncio.sleep(5)
            yield compose
    
    async def send_spellcheck_request(
        self,
        producer: AIOKafkaProducer,
        essay_id: str,
        text: str,
        correlation_id: str,
        language: str = "en"
    ):
        """Send a spellcheck request to Kafka."""
        request_data = EssayLifecycleSpellcheckRequestV1(
            text_storage_id=f"test-storage-{essay_id}",
            entity_ref=EntityReference(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=f"batch-{uuid4()}",
            ),
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=essay_id, entity_type="essay"),
                timestamp=datetime.now(UTC),
                started_at=datetime.now(UTC),
                processing_stage=ProcessingStage.SPELLCHECK,
                event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            ),
            language=language,
        )
        
        envelope = EventEnvelope(
            event_type=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            source_service="test-service",
            correlation_id=UUID(correlation_id),
            data=request_data,
        )
        
        topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
        await producer.send(
            topic,
            value=envelope.model_dump_json().encode(),
            key=essay_id.encode()
        )
    
    async def wait_for_result(
        self,
        consumer: AIOKafkaConsumer,
        correlation_id: str,
        timeout: float = 30.0
    ) -> tuple[SpellcheckResultDataV1, float]:
        """Wait for spellcheck result and measure processing time."""
        start_time = time.time()
        
        async def consume():
            async for msg in consumer:
                try:
                    envelope = EventEnvelope[SpellcheckResultDataV1].model_validate_json(
                        msg.value.decode()
                    )
                    if str(envelope.correlation_id) == correlation_id:
                        processing_time = time.time() - start_time
                        return envelope.data, processing_time
                except Exception as e:
                    print(f"Error parsing message: {e}")
                    continue
        
        try:
            return await asyncio.wait_for(consume(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Timeout waiting for result after {timeout}s")
    
    @pytest.mark.asyncio
    async def test_problematic_essay_performance(
        self,
        kafka_container,
        spellchecker_service
    ):
        """Test performance with essay containing problematic words."""
        # Setup Kafka producer and consumer
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            value_serializer=lambda v: v
        )
        await producer.start()
        
        consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            auto_offset_reset='earliest',
            value_deserializer=lambda v: v
        )
        await consumer.start()
        
        try:
            # Send problematic essay
            correlation_id = str(uuid4())
            essay_id = "problematic-essay-001"
            
            print(f"\n=== Testing Problematic Essay ===")
            print(f"Essay length: {len(self.PROBLEMATIC_ESSAY)} chars")
            print(f"Contains: overconsumption, overconsuming, children's, short-term, career-suicide")
            
            await self.send_spellcheck_request(
                producer,
                essay_id,
                self.PROBLEMATIC_ESSAY,
                correlation_id
            )
            
            # Wait for result and measure time
            result, processing_time = await self.wait_for_result(consumer, correlation_id)
            
            print(f"\nProcessing time: {processing_time:.3f}s")
            print(f"Corrections made: {result.corrections_made}")
            print(f"Status: {result.status}")
            
            # With current implementation, this should take > 5 seconds
            assert processing_time > 3.0, \
                f"Expected slow processing (>3s) but took only {processing_time:.3f}s"
            
            # Should still complete successfully
            assert result.status == EssayStatus.SPELLCHECKED_SUCCESS
            
        finally:
            await producer.stop()
            await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_normal_essay_performance(
        self,
        kafka_container,
        spellchecker_service
    ):
        """Test performance with normal essay for comparison."""
        # Normal essay without problematic words
        normal_essay = """
        This is a normal essay with some simple errors. The student recieve their
        grades yesterday. They were very happy becouse they got good marks. The
        teacher said their writting had improved significantly this semester.
        """
        
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            value_serializer=lambda v: v
        )
        await producer.start()
        
        consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            auto_offset_reset='earliest',
            value_deserializer=lambda v: v
        )
        await consumer.start()
        
        try:
            correlation_id = str(uuid4())
            essay_id = "normal-essay-001"
            
            print(f"\n=== Testing Normal Essay ===")
            print(f"Essay length: {len(normal_essay)} chars")
            
            await self.send_spellcheck_request(
                producer,
                essay_id,
                normal_essay,
                correlation_id
            )
            
            result, processing_time = await self.wait_for_result(consumer, correlation_id)
            
            print(f"\nProcessing time: {processing_time:.3f}s")
            print(f"Corrections made: {result.corrections_made}")
            
            # Normal essays should process quickly
            assert processing_time < 1.0, \
                f"Normal essay took too long: {processing_time:.3f}s"
            
        finally:
            await producer.stop()
            await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_batch_performance_analysis(
        self,
        kafka_container,
        spellchecker_service
    ):
        """Test batch of essays to identify performance patterns."""
        test_essays = [
            # Fast essays
            ("fast-1", "This is a simple text with one eror."),
            ("fast-2", "The studnet wrote their essay yesterday."),
            
            # Slow essays (with problematic words)
            ("slow-1", "The overconsumption problem is serious."),
            ("slow-2", "Children's education is important for our future."),
            ("slow-3", "This is a short-term solution to the problem."),
        ]
        
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            value_serializer=lambda v: v
        )
        await producer.start()
        
        consumer = AIOKafkaConsumer(
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            auto_offset_reset='earliest',
            value_deserializer=lambda v: v
        )
        await consumer.start()
        
        try:
            results = []
            
            # Send all essays
            for essay_id, text in test_essays:
                correlation_id = str(uuid4())
                await self.send_spellcheck_request(
                    producer,
                    essay_id,
                    text,
                    correlation_id
                )
                
                # Wait for result
                result, processing_time = await self.wait_for_result(
                    consumer,
                    correlation_id,
                    timeout=10.0
                )
                
                results.append({
                    "essay_id": essay_id,
                    "text_length": len(text),
                    "processing_time": processing_time,
                    "corrections": result.corrections_made,
                })
            
            # Analyze results
            print(f"\n=== Batch Performance Analysis ===")
            print(f"{'Essay ID':<10} {'Length':<8} {'Time (s)':<10} {'Corrections':<12}")
            print("-" * 45)
            
            for r in results:
                print(f"{r['essay_id']:<10} {r['text_length']:<8} "
                      f"{r['processing_time']:<10.3f} {r['corrections']:<12}")
            
            # Verify performance patterns
            fast_times = [r["processing_time"] for r in results if r["essay_id"].startswith("fast")]
            slow_times = [r["processing_time"] for r in results if r["essay_id"].startswith("slow")]
            
            avg_fast = sum(fast_times) / len(fast_times)
            avg_slow = sum(slow_times) / len(slow_times)
            
            print(f"\nAverage fast essay time: {avg_fast:.3f}s")
            print(f"Average slow essay time: {avg_slow:.3f}s")
            print(f"Slowdown factor: {avg_slow / avg_fast:.1f}x")
            
            # Slow essays should be significantly slower
            assert avg_slow > avg_fast * 3, \
                f"Expected slow essays to be >3x slower, but got {avg_slow/avg_fast:.1f}x"
            
        finally:
            await producer.stop()
            await consumer.stop()


if __name__ == "__main__":
    # Note: This requires Docker to be running
    pytest.main([__file__, "-v", "-s"])