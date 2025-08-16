#!/usr/bin/env python3
"""Debug script to test pipeline progression issue."""

import asyncio
import json
import time
from uuid import uuid4

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from common_core.events import EventEnvelope
from common_core.models import ClientBatchPipelineRequestV1
from common_core.pipeline_models import PhaseName
from common_core.util import topic_name


async def main():
    # Create a simple test batch
    batch_id = str(uuid4())
    correlation_id = str(uuid4())
    
    print(f"Test batch_id: {batch_id}")
    print(f"Test correlation_id: {correlation_id}")
    
    # First register the batch
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/v1/batch/register",
            json={
                "batch_id": batch_id,
                "class_id": "test-class-123",
                "course_code": "TEST101",
                "user_id": "test-user",
                "batch_type": "REGULAR",
                "essay_instruction": "Test essay",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        print(f"Batch registration response: {response.status_code}")
    
    # Mark batch as ready (simulate essays being ready)
    # This would normally happen through the file upload and essay ready flow
    # For now, we'll skip this and just send a pipeline request
    
    # Send pipeline request via Kafka
    producer = AIOKafkaProducer(
        bootstrap_servers="localhost:9092",
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await producer.start()
    
    try:
        pipeline_request = ClientBatchPipelineRequestV1(
            batch_id=batch_id,
            requested_pipeline="nlp",  # This should resolve to [spellcheck, nlp]
        )
        
        envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type="client.batch.pipeline.request",
            correlation_id=correlation_id,
            source_service="debug-script",
            data=pipeline_request.model_dump(),
        )
        
        topic = topic_name("batch.pipeline")
        print(f"Sending pipeline request to topic: {topic}")
        
        await producer.send(
            topic,
            value=envelope.model_dump(),
        )
        
        print("Pipeline request sent. Waiting for processing...")
        
        # Give it some time to process
        await asyncio.sleep(10)
        
        # Check the logs
        print("\nCheck docker logs for DEBUG messages:")
        print("docker logs huleedu_batch_orchestrator_service 2>&1 | grep DEBUG")
        
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())