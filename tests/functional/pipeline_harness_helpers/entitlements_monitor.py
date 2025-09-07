"""Entitlements event monitoring helper for pipeline tests."""

import asyncio
import json
from typing import Any, Dict

from structlog import get_logger

logger = get_logger(__name__)


class EntitlementsMonitorHelper:
    """Helper class for monitoring Entitlements events during pipeline execution."""

    @staticmethod
    def create_entitlements_tracker() -> Dict[str, bool]:
        """
        Create a tracker for Entitlements events.

        Returns:
            Dictionary tracking balance_changed and usage_recorded events
        """
        return {"balance_changed": False, "usage_recorded": False}

    @staticmethod
    def is_entitlements_event(topic: str) -> bool:
        """
        Check if a topic is an Entitlements event.

        Args:
            topic: Kafka topic name

        Returns:
            True if this is an Entitlements event topic
        """
        return topic in [
            "huleedu.entitlements.credit.balance.changed.v1",
            "huleedu.entitlements.usage.recorded.v1",
        ]

    @staticmethod
    def process_entitlements_event(
        topic: str,
        envelope_data: Dict[str, Any],
        tracker: Dict[str, bool],
    ) -> None:
        """
        Process an Entitlements event and update tracker.

        Args:
            topic: Kafka topic name
            envelope_data: Event envelope data
            tracker: Entitlements event tracker to update
        """
        if topic == "huleedu.entitlements.credit.balance.changed.v1":
            tracker["balance_changed"] = True
            logger.debug(
                "💳 Credit balance changed observed",
                correlation_id=envelope_data.get("correlation_id"),
            )
        elif topic == "huleedu.entitlements.usage.recorded.v1":
            tracker["usage_recorded"] = True
            event_data = envelope_data.get("data", {})
            logger.debug(
                "💳 Usage recorded observed",
                correlation_id=envelope_data.get("correlation_id"),
                operation_type=event_data.get("operation_type"),
                amount=event_data.get("amount"),
                metric_name=event_data.get("metadata", {}).get("metric_name"),
            )

    @staticmethod
    async def wait_for_entitlements_events(
        consumer: Any,
        correlation_id: str,
        timeout_seconds: int = 30,
    ) -> Dict[str, bool]:
        """
        Wait specifically for Entitlements credit events.

        This is used when Entitlements events weren't captured during pipeline
        monitoring (e.g., if they arrive after pipeline completion).

        Args:
            consumer: Kafka consumer instance
            correlation_id: Correlation ID to filter events
            timeout_seconds: Maximum wait time

        Returns:
            Dictionary with balance_changed and usage_recorded status
        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        tracker = EntitlementsMonitorHelper.create_entitlements_tracker()

        logger.info(
            "⏳ Waiting for Entitlements events",
            correlation_id=correlation_id[:8],
            timeout=timeout_seconds,
        )

        while asyncio.get_event_loop().time() < end_time:
            # Check if we've seen both events
            if tracker["balance_changed"] and tracker["usage_recorded"]:
                logger.info("✅ Both Entitlements events observed")
                return tracker

            try:
                msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

                for topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")

                            # Filter by correlation ID
                            if event_correlation_id != correlation_id:
                                continue

                            # Process if it's an Entitlements event
                            if EntitlementsMonitorHelper.is_entitlements_event(message.topic):
                                EntitlementsMonitorHelper.process_entitlements_event(
                                    message.topic,
                                    envelope_data,
                                    tracker,
                                )

                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"Failed to parse Entitlements message: {e}")
                            continue

            except Exception as e:
                logger.warning(f"Error polling for Entitlements events: {e}")
                await asyncio.sleep(1)

        logger.warning(
            f"⚠️ Entitlements events timeout after {timeout_seconds}s",
            balance_changed=tracker["balance_changed"],
            usage_recorded=tracker["usage_recorded"],
        )
        return tracker

    @staticmethod
    def validate_credit_consumption(
        entitlements_events: Dict[str, bool],
        expected_events: bool = True,
    ) -> bool:
        """
        Validate that expected Entitlements events were observed.

        Args:
            entitlements_events: Tracker dictionary from monitoring
            expected_events: Whether we expect to see the events

        Returns:
            True if validation passes
        """
        if expected_events:
            if not entitlements_events["balance_changed"]:
                logger.error("❌ Credit balance changed event not observed")
                return False
            if not entitlements_events["usage_recorded"]:
                logger.error("❌ Usage recorded event not observed")
                return False
            logger.info("✅ All expected Entitlements events observed")
            return True
        else:
            # For tests expecting no consumption (e.g., credit denial)
            if entitlements_events["balance_changed"] or entitlements_events["usage_recorded"]:
                logger.error("❌ Unexpected Entitlements events observed")
                return False
            logger.info("✅ No Entitlements events observed (as expected)")
            return True
