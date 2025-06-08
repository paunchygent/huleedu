"""
Walking Skeleton End-to-End Test - Excess Content Handling.

This test validates ELS handling of excess content (more files than essay slots)
and the ExcessContentProvisionedV1 event emission.
"""

import asyncio

import aiohttp
import pytest

from .walking_skeleton_e2e_utils import CONFIG, TOPICS, EventCollector, logger


@pytest.mark.asyncio
async def test_excess_content_handling():
    """
    Test ELS handling of excess content (more files than essay slots).

    This validates the ExcessContentProvisionedV1 event emission.
    """

    test_data = {
        "batch_id": None,
        "essay_ids": ["excess-test-essay-001"],  # Only 1 slot
        "course_code": "ENG104",
        "class_designation": "Fall2024-ExcessContent-Test",
    }

    # Start event collection
    event_collector = EventCollector(CONFIG["kafka_bootstrap_servers"])
    collection_task = asyncio.create_task(
        event_collector.start_collecting(
            [TOPICS["excess_content"], TOPICS["content_provisioned"]], timeout=60
        )
    )

    await asyncio.sleep(2)

    try:
        async with aiohttp.ClientSession() as session:
            # Register batch with 1 essay slot
            registration_payload = {
                "expected_essay_count": 1,
                "essay_ids": test_data["essay_ids"],
                "course_code": test_data["course_code"],
                "class_designation": test_data["class_designation"],
                "essay_instructions": "Excess content test",
                "teacher_name": "Test Teacher",
            }

            async with session.post(
                f"{CONFIG['bos_url']}/v1/batches/register", json=registration_payload
            ) as response:
                assert response.status == 202
                response_data = await response.json()
                test_data["batch_id"] = response_data["batch_id"]

            logger.info(f"Registered batch with 1 slot: {test_data['batch_id']}")

            # Upload 3 files (2 excess)
            data = aiohttp.FormData()
            data.add_field("batch_id", test_data["batch_id"])

            for i in range(3):
                content = f"Test essay content {i + 1} for excess handling validation"
                data.add_field(
                    "files", content, filename=f"essay{i + 1}.txt", content_type="text/plain"
                )

            async with session.post(
                f"{CONFIG['file_service_url']}/v1/files/batch", data=data
            ) as response:
                assert response.status == 202

            logger.info("Uploaded 3 files to batch with 1 slot")

            # Wait for ELS processing
            await asyncio.sleep(10)

            # Validate excess content events
            batch_id_str = str(test_data["batch_id"])
            excess_events = event_collector.get_events_for_batch(
                TOPICS["excess_content"], batch_id_str
            )

            # Should have 2 excess content events (3 files - 1 slot = 2 excess)
            assert len(excess_events) == 2, (
                f"Expected 2 excess content events, got {len(excess_events)}"
            )
            logger.info("✓ Excess content properly handled with ExcessContentProvisionedV1 events")

            # Validate regular content provisioned events
            content_events = event_collector.get_events_for_batch(
                TOPICS["content_provisioned"], batch_id_str
            )
            assert len(content_events) == 3, (
                f"Expected 3 content provisioned events, got {len(content_events)}"
            )
            logger.info("✓ All content provisioned events emitted correctly")

    finally:
        event_collector.stop_collecting()
        collection_task.cancel()
        try:
            await collection_task
        except asyncio.CancelledError:
            pass
