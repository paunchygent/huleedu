"""Event waiting helper for pipeline tests."""

import asyncio
import json
from typing import Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.event_waiters")


class EventWaitingHelper:
    """Helper class for waiting on specific Kafka events during pipeline execution."""

    @staticmethod
    async def wait_for_student_matching_events(
        consumer: Any,
        correlation_id: str,
        timeout_seconds: int = 60,
    ) -> Optional[Dict[str, Any]]:
        """
        Monitor Phase 2 student matching events.

        Args:
            consumer: Kafka consumer instance
            correlation_id: Correlation ID to filter events
            timeout_seconds: Timeout for waiting

        Returns:
            The author.matches.suggested event envelope if found, None otherwise
        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        matching_initiated = False
        matching_requested = False

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: Dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")

                            # Filter by correlation ID
                            if event_correlation_id != correlation_id:
                                continue

                            # Track student matching flow
                            if "student.matching.initiate.command" in event_type:
                                matching_initiated = True
                                logger.info("📨 BOS initiated student matching")

                            elif "student.matching.requested" in event_type:
                                matching_requested = True
                                logger.info("📨 ELS requested student matching from NLP")

                            elif "author.matches.suggested" in event_type:
                                logger.info("📨 NLP suggested student-essay associations")
                                return envelope_data

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        logger.error(
            f"Timeout waiting for student matching events. "
            f"Initiated: {matching_initiated}, Requested: {matching_requested}"
        )
        return None

    @staticmethod
    async def wait_for_guest_batch_ready(
        consumer: Any,
        correlation_id: str,
        timeout_seconds: int = 10,
    ) -> bool:
        """
        Wait for BatchContentProvisioningCompleted event for GUEST batches.

        Args:
            consumer: Kafka consumer instance
            correlation_id: Correlation ID to filter events
            timeout_seconds: Timeout for waiting

        Returns:
            True if the event was received, False otherwise
        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: Dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")

                            # Check for BatchContentProvisioningCompleted (GUEST batch flow)
                            if (
                                event_correlation_id == correlation_id
                                and "batch.content.provisioning.completed" in event_type
                            ):
                                logger.info(
                                    "📨 BatchContentProvisioningCompleted received - "
                                    "GUEST batch ready for pipeline!"
                                )
                                return True

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        return False

    @staticmethod
    async def wait_for_batch_essays_ready(
        consumer: Any,
        correlation_id: str,
        timeout_seconds: int = 30,
    ) -> bool:
        """
        Wait for BatchEssaysReady event after associations are confirmed.

        Args:
            consumer: Kafka consumer instance
            correlation_id: Correlation ID to filter events
            timeout_seconds: Timeout for waiting

        Returns:
            True if the event was received, False otherwise
        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: Dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")

                            # Check for our event
                            if (
                                event_correlation_id == correlation_id
                                and "batch.essays.ready" in event_type
                            ):
                                logger.info(
                                    "📨 BatchEssaysReady received - batch ready for pipeline!"
                                )
                                return True

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        return False
