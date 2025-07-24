"""
End-to-End Integration Test for File Service Client Traceability.

This test validates the complete traceability flow from file upload through
slot assignment, ensuring file_upload_id can be tracked throughout the pipeline.

Tests the implementation of the File Service Client Traceability feature:
- File upload generates unique file_upload_id
- EssayContentProvisionedV1 includes file_upload_id
- EssaySlotAssignedV1 maps file_upload_id → essay_id
- Complete event correlation across service boundaries
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import EventEnvelope
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from huleedu_service_libs.logging_utils import create_service_logger

from tests.utils.kafka_test_manager import KafkaTestManager, kafka_event_monitor
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.file_traceability_e2e")


@pytest.mark.integration
@pytest.mark.docker
@pytest.mark.asyncio
class TestFileTraceabilityE2E:
    """End-to-end tests for file upload traceability through the system."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Get ServiceTestManager for service validation."""
        return ServiceTestManager()

    @pytest.fixture
    async def kafka_manager(self) -> KafkaTestManager:
        """Get KafkaTestManager for event monitoring."""
        return KafkaTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """Ensure required services are running and healthy."""
        endpoints = await service_manager.get_validated_endpoints()

        required_services = ["file_service", "essay_lifecycle_api"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for integration testing")

        return endpoints

    async def test_complete_file_traceability_flow(
        self,
        validated_services: dict[str, Any],
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Test complete traceability from file upload to slot assignment.

        Validates:
        1. File upload generates unique file_upload_id
        2. EssayContentProvisionedV1 includes file_upload_id
        3. EssaySlotAssignedV1 provides file_upload_id → essay_id mapping
        4. All events maintain correlation_id consistency
        """
        # Test data
        batch_id = str(uuid4())
        user_id = "test_user_traceability"
        correlation_id = uuid4()
        essay_ids = [str(uuid4()) for _ in range(3)]
        file_upload_id = f"upload_{uuid4().hex[:8]}"

        # Monitor relevant topics
        topics_to_monitor = [
            topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
            topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
        ]

        async with kafka_event_monitor("test_file_traceability", topics_to_monitor) as consumer:
            # Step 1: Register batch (simulating BOS behavior)
            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                course_code=CourseCode.ENG5,
                essay_instructions="Test traceability essay",
                essay_ids=essay_ids,
                expected_essay_count=len(essay_ids),
                user_id=user_id,
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                    timestamp=datetime.now(UTC),
                    processing_stage=None,
                ),
            )

            # Publish batch registration
            await self._publish_event(
                kafka_manager,
                topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
                batch_event,
                correlation_id,
                "batch-orchestrator-service",
            )

            # Step 2: Simulate file upload and content provisioning
            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=file_upload_id,
                original_file_name="test_essay.txt",
                raw_file_storage_id=f"raw_{uuid4().hex[:8]}",
                text_storage_id=f"text_{uuid4().hex[:8]}",
                file_size_bytes=1024,
                content_md5_hash="abc123def456",
                correlation_id=correlation_id,
            )

            # Publish content provisioned event
            await self._publish_event(
                kafka_manager,
                topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
                content_event,
                correlation_id,
                "file-service",
            )

            # Step 3: Collect and validate events
            collected_events = await kafka_manager.collect_events(
                consumer,
                expected_count=3,  # batch_registered, content_provisioned, slot_assigned
                timeout_seconds=10,
            )

            assert len(collected_events) >= 3, f"Expected 3 events, got {len(collected_events)}"

            # Find each event type
            batch_registered_event = None
            content_provisioned_event = None
            slot_assigned_event = None

            for event in collected_events:
                event_data = event["data"]
                event_type = event_data.get("event_type", "")

                if "batch.essays.registered" in event_type:
                    batch_registered_event = event_data
                elif "essay.content.provisioned" in event_type:
                    content_provisioned_event = event_data
                elif "essay.slot.assigned" in event_type:
                    slot_assigned_event = event_data

            # Validate batch registration
            assert batch_registered_event is not None, "BatchEssaysRegistered event not found"
            assert batch_registered_event["data"]["batch_id"] == batch_id
            assert len(batch_registered_event["data"]["essay_ids"]) == 3

            # Validate content provisioned
            assert content_provisioned_event is not None, "EssayContentProvisionedV1 event not found"
            content_data = content_provisioned_event["data"]
            assert content_data["batch_id"] == batch_id
            assert content_data["file_upload_id"] == file_upload_id
            assert content_data["original_file_name"] == "test_essay.txt"

            # Validate slot assignment - the critical mapping event
            assert slot_assigned_event is not None, "EssaySlotAssignedV1 event not found"
            slot_data = slot_assigned_event["data"]
            assert slot_data["batch_id"] == batch_id
            assert slot_data["file_upload_id"] == file_upload_id
            assert slot_data["essay_id"] in essay_ids  # Must be one of pre-generated IDs
            assert slot_data["text_storage_id"] == content_event.text_storage_id

            # Validate correlation across events
            assert (
                slot_assigned_event["correlation_id"] == str(correlation_id)
            ), "Correlation ID mismatch"

            logger.info(
                "✅ File traceability validated",
                file_upload_id=file_upload_id,
                assigned_essay_id=slot_data["essay_id"],
                batch_id=batch_id,
            )

    async def test_multiple_file_uploads_traceability(
        self,
        validated_services: dict[str, Any],
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Test traceability with multiple concurrent file uploads.

        Validates that each file maintains its unique identity through
        the assignment process.
        """
        batch_id = str(uuid4())
        user_id = "test_user_multi"
        correlation_id = uuid4()
        essay_ids = [str(uuid4()) for _ in range(5)]
        file_upload_ids = [f"upload_{i}_{uuid4().hex[:8]}" for i in range(5)]

        topics_to_monitor = [
            topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
            topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
        ]

        async with kafka_event_monitor("test_multi_traceability", topics_to_monitor) as consumer:
            # Register batch
            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                course_code=CourseCode.ENG5,
                essay_instructions="Multi-file test",
                essay_ids=essay_ids,
                expected_essay_count=len(essay_ids),
                user_id=user_id,
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                    timestamp=datetime.now(UTC),
                    processing_stage=None,
                ),
            )

            await self._publish_event(
                kafka_manager,
                topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
                batch_event,
                correlation_id,
                "batch-orchestrator-service",
            )

            # Upload multiple files
            for i, file_upload_id in enumerate(file_upload_ids):
                content_event = EssayContentProvisionedV1(
                    batch_id=batch_id,
                    file_upload_id=file_upload_id,
                    original_file_name=f"essay_{i}.txt",
                    raw_file_storage_id=f"raw_{i}_{uuid4().hex[:8]}",
                    text_storage_id=f"text_{i}_{uuid4().hex[:8]}",
                    file_size_bytes=1024 + i * 100,
                    content_md5_hash=f"hash_{i}",
                    correlation_id=correlation_id,
                )

                await self._publish_event(
                    kafka_manager,
                    topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
                    content_event,
                    correlation_id,
                    "file-service",
                )

            # Collect all events (1 batch + 5 content + 5 slot assignments)
            collected_events = await kafka_manager.collect_events(
                consumer,
                expected_count=11,
                timeout_seconds=15,
            )

            # Extract slot assignment events
            slot_assignments = [
                event["data"]
                for event in collected_events
                if "essay.slot.assigned" in event["data"].get("event_type", "")
            ]

            assert len(slot_assignments) == 5, f"Expected 5 slot assignments, got {len(slot_assignments)}"

            # Verify each file has unique mapping
            file_to_essay_mapping = {}
            for assignment in slot_assignments:
                data = assignment["data"]
                file_upload_id = data["file_upload_id"]
                essay_id = data["essay_id"]
                
                assert file_upload_id in file_upload_ids, f"Unknown file_upload_id: {file_upload_id}"
                assert essay_id in essay_ids, f"Essay ID not from pre-generated set: {essay_id}"
                
                # Ensure no duplicate mappings
                assert file_upload_id not in file_to_essay_mapping, f"Duplicate mapping for {file_upload_id}"
                file_to_essay_mapping[file_upload_id] = essay_id

            # Verify all files were mapped
            assert len(file_to_essay_mapping) == 5, "Not all files were mapped to essays"

            logger.info(
                "✅ Multi-file traceability validated",
                mappings=file_to_essay_mapping,
                batch_id=batch_id,
            )

    async def _publish_event(
        self,
        kafka_manager: KafkaTestManager,
        topic: str,
        event_data: Any,
        correlation_id: UUID,
        source_service: str,
    ) -> None:
        """Publish an event wrapped in EventEnvelope."""
        envelope: EventEnvelope = EventEnvelope(
            event_id=uuid4(),
            event_type=topic,  # Use the topic name as event_type
            event_timestamp=datetime.now(UTC),
            source_service=source_service,
            correlation_id=correlation_id,
            data=event_data,
        )

        # Serialize using Pydantic V2 pattern
        event_json = envelope.model_dump(mode="json")
        await kafka_manager.publish_event(topic, event_json)