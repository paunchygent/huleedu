"""
Diagnostic test for Entitlements event chain.

This isolated test helps understand:
1. Whether Entitlements receives ResourceConsumptionV1 events
2. Whether Entitlements publishes CreditBalanceChanged and UsageRecorded events
3. How long the two-hop event chain takes
4. Whether correlation IDs are preserved correctly

This test publishes a single ResourceConsumptionV1 event and monitors for
the resulting Entitlements events, with detailed logging at each step.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core import (
    EventEnvelope,
    ProcessingEvent,
    topic_name,
)
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from structlog import get_logger

from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


class TestEntitlementsEventChainDiagnostic:
    """Diagnostic test for understanding Entitlements event processing."""

    @pytest.mark.asyncio
    @pytest.mark.docker
    @pytest.mark.timeout(120)
    async def test_entitlements_event_chain_isolated(self) -> None:
        """
        Isolated test to understand Entitlements event processing chain.

        This test:
        1. Seeds credits for a test user
        2. Publishes a ResourceConsumptionV1 event directly to Kafka
        3. Monitors Entitlements topics for resulting events
        4. Logs timing and correlation details
        """
        # Setup
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_manager = KafkaTestManager()

        # Test data
        test_user_id = f"test-user-{uuid.uuid4().hex[:8]}"
        test_correlation_id = str(uuid.uuid4())
        test_batch_id = str(uuid.uuid4())

        logger.info(
            "🔬 Starting Entitlements event chain diagnostic",
            user_id=test_user_id,
            correlation_id=test_correlation_id,
            batch_id=test_batch_id,
        )

        # Ensure services are healthy
        endpoints = await service_manager.get_validated_endpoints()
        assert "entitlements_service" in endpoints, "Entitlements service not available"
        logger.info(f"✅ {len(endpoints)} services validated healthy")

        # Seed user with credits
        teacher_user = auth_manager.create_test_user(role="teacher", user_id=test_user_id)
        logger.info(f"💳 Seeding user {test_user_id} with 1000 credits")

        seed_response = await service_manager.make_request(
            method="POST",
            service="entitlements_service",
            path="/v1/admin/credits/set",
            json={
                "subject_type": "user",
                "subject_id": test_user_id,
                "balance": 1000,
            },
            user=teacher_user,
            correlation_id=test_correlation_id,
        )
        assert seed_response.get("success") is True
        logger.info(f"✅ Credits seeded: {seed_response}")

        # Setup Kafka monitoring BEFORE publishing
        entitlements_topics = [
            topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED),
            topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED),
        ]

        # Use unique consumer group to avoid offset issues
        consumer_group = f"diagnostic-{uuid.uuid4().hex[:8]}"
        logger.info(f"📡 Setting up Kafka consumer: group={consumer_group}")

        # Create consumer with earliest offset to catch all events
        consumer = AIOKafkaConsumer(
            *entitlements_topics,
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            group_id=consumer_group,
            auto_offset_reset="earliest",  # Start from beginning
            enable_auto_commit=False,  # Manual control
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        )

        await consumer.start()
        # Don't seek to end - we want to see all events
        logger.info(f"✅ Consumer started, subscribed to: {entitlements_topics}")

        # Publish ResourceConsumptionV1 event
        logger.info("📤 Publishing ResourceConsumptionV1 event to Kafka")

        resource_event = ResourceConsumptionV1(
            entity_type="batch",
            entity_id=test_batch_id,
            user_id=test_user_id,
            org_id=None,
            resource_type="cj_comparison",  # Use singular to match policy
            quantity=10,
            service_name="test_diagnostic",
            processing_id=f"test-{uuid.uuid4().hex[:8]}",
            consumed_at=datetime.now(timezone.utc),
        )

        envelope = EventEnvelope[ResourceConsumptionV1](
            event_id=uuid.uuid4(),
            event_type=topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
            event_timestamp=datetime.now(timezone.utc),
            source_service="test_diagnostic",
            correlation_id=uuid.UUID(test_correlation_id),
            data=resource_event,
            metadata={
                "partition_key": test_user_id,
                "batch_id": test_batch_id,
            },
        )

        # Publish directly to Kafka
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v.model_dump(mode="json")).encode("utf-8"),
        )
        await producer.start()

        try:
            await producer.send_and_wait(
                topic=topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
                value=envelope,
                key=test_user_id.encode("utf-8"),
            )
            logger.info(f"✅ ResourceConsumptionV1 published at {time.time()}")
        finally:
            await producer.stop()

        # Monitor for resulting Entitlements events
        logger.info("👀 Monitoring for Entitlements events...")

        found_balance_changed = False
        found_usage_recorded = False
        events_found: list[dict[str, Any]] = []

        start_time = time.time()
        timeout = 60  # 60 seconds should be plenty for two-hop chain

        while time.time() - start_time < timeout:
            try:
                # Poll for messages with short timeout
                msg_batch = await consumer.getmany(timeout_ms=500, max_records=100)

                for topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            event_data = message.value
                            if not isinstance(event_data, dict):
                                continue

                            event_type = event_data.get("event_type", "")
                            event_correlation = event_data.get("correlation_id", "")

                            # Log ALL events we see for debugging
                            logger.info(
                                f"📨 Event received: {event_type}",
                                correlation_id=event_correlation,
                                topic=message.topic,
                                offset=message.offset,
                                timestamp=message.timestamp,
                                elapsed=f"{time.time() - start_time:.2f}s",
                            )

                            # Check if this is our event
                            if event_correlation == test_correlation_id:
                                logger.info(
                                    f"🎯 FOUND OUR EVENT: {event_type}",
                                    elapsed=f"{time.time() - start_time:.2f}s",
                                )
                                events_found.append(event_data)

                                if "credit.balance.changed" in event_type:
                                    found_balance_changed = True
                                elif "usage.recorded" in event_type:
                                    found_usage_recorded = True

                                # Check if we have both
                                if found_balance_changed and found_usage_recorded:
                                    logger.info(
                                        f"✅ Both Entitlements events found in "
                                        f"{time.time() - start_time:.2f}s"
                                    )
                                    break
                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

                if found_balance_changed and found_usage_recorded:
                    break

            except asyncio.TimeoutError:
                # Normal - just means no messages in this poll
                pass

            # Small sleep to avoid busy waiting
            await asyncio.sleep(0.1)

        # Stop consumer
        await consumer.stop()

        # Analyze results
        elapsed = time.time() - start_time
        logger.info(f"⏱️ Total monitoring time: {elapsed:.2f}s")

        if found_balance_changed and found_usage_recorded:
            logger.info(
                "✅ SUCCESS: Both events found",
                balance_changed=found_balance_changed,
                usage_recorded=found_usage_recorded,
                total_events_found=len(events_found),
            )

            # Log event details for analysis
            for event in events_found:
                logger.info(
                    "Event details",
                    event_type=event.get("event_type"),
                    correlation_id=event.get("correlation_id"),
                    source_service=event.get("source_service"),
                    data=event.get("data"),
                )
        else:
            logger.error(
                f"❌ FAILURE: Events not found within {timeout}s",
                balance_changed=found_balance_changed,
                usage_recorded=found_usage_recorded,
                total_events_found=len(events_found),
            )

            # Check if credits were actually consumed via API
            logger.info("🔍 Checking if credits were consumed via API...")
            operations = await service_manager.make_request(
                method="GET",
                service="entitlements_service",
                path=f"/v1/admin/credits/operations?correlation_id={test_correlation_id}",
                user=teacher_user,
                correlation_id=test_correlation_id,
            )

            if operations.get("operations"):
                logger.info(
                    "✅ API confirms consumption occurred",
                    operations=operations.get("operations"),
                )
            else:
                logger.error(
                    "❌ API shows no consumption - Entitlements may not have received the event"
                )

        # Assertions
        assert found_balance_changed, f"CreditBalanceChanged event not found within {timeout}s"
        assert found_usage_recorded, f"UsageRecorded event not found within {timeout}s"

        logger.info("🎯 Diagnostic test complete - event chain verified")


@pytest.mark.asyncio
@pytest.mark.docker
@pytest.mark.timeout(30)
async def test_direct_consumption_produces_events() -> None:
    """
    Even simpler test: Call Entitlements consume API directly and check for events.

    This bypasses ResourceConsumptionV1 to isolate just the Entitlements publishing.
    """
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    kafka_manager = KafkaTestManager()

    test_user_id = f"direct-test-{uuid.uuid4().hex[:8]}"
    test_correlation_id = str(uuid.uuid4())

    logger.info("🔬 Testing direct Entitlements consumption")

    # Seed credits
    teacher_user = auth_manager.create_test_user(role="teacher", user_id=test_user_id)
    await service_manager.make_request(
        method="POST",
        service="entitlements_service",
        path="/v1/admin/credits/set",
        json={"subject_type": "user", "subject_id": test_user_id, "balance": 100},
        user=teacher_user,
        correlation_id=test_correlation_id,
    )

    # Setup consumer
    topics = [
        topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED),
        topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED),
    ]

    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=kafka_manager.config.bootstrap_servers,
        group_id=f"direct-diagnostic-{uuid.uuid4().hex[:8]}",
        auto_offset_reset="latest",  # Only new events
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
    )

    await consumer.start()
    await consumer.seek_to_end()  # Start from now

    # Consume credits directly via API
    logger.info("💳 Consuming credits via API...")
    response = await service_manager.make_request(
        method="POST",
        service="entitlements_service",
        path="/v1/entitlements/consume-credits",
        json={
            "user_id": test_user_id,
            "metric": "cj_comparison",  # Use singular to match policy
            "amount": 5,
            "correlation_id": test_correlation_id,
        },
        user=teacher_user,
        correlation_id=test_correlation_id,
    )

    assert response.get("success") is True
    logger.info(f"✅ Credits consumed: {response}")

    # Monitor for events
    found_events = []
    start = time.time()

    while time.time() - start < 15:  # 15 seconds should be enough
        msg_batch = await consumer.getmany(timeout_ms=500, max_records=100)

        for _, messages in msg_batch.items():
            for msg in messages:
                event = msg.value
                if event and event.get("correlation_id") == test_correlation_id:
                    logger.info(f"🎯 Found event: {event.get('event_type')}")
                    found_events.append(event)

        if len(found_events) >= 2:  # Both events found
            break

        await asyncio.sleep(0.1)

    await consumer.stop()

    # Check results
    event_types = [e.get("event_type") for e in found_events]
    logger.info(f"Found {len(found_events)} events: {event_types}")

    assert len(found_events) >= 2, f"Expected 2 events, found {len(found_events)}"
    logger.info("✅ Direct consumption produces events successfully")
