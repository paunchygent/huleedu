from __future__ import annotations

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.event_utils import (
    extract_correlation_id_as_string,
    extract_user_id_from_event_data,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

from services.class_management_service.protocols import ClassEventPublisherProtocol

logger = create_service_logger("class_management_service.event_publisher")


class DefaultClassEventPublisherImpl(ClassEventPublisherProtocol):
    """Default implementation of ClassEventPublisherProtocol using KafkaBus and Redis."""

    def __init__(
        self, kafka_bus: KafkaPublisherProtocol, redis_client: AtomicRedisClientProtocol
    ) -> None:
        self.kafka_bus = kafka_bus
        self.redis_client = redis_client

    async def publish_class_event(self, event_envelope: EventEnvelope) -> None:
        """Publish event to both Kafka and Redis for real-time updates."""
        # 1. Publish to Kafka (existing behavior)
        topic = event_envelope.event_type
        await self.kafka_bus.publish(topic, event_envelope)

        # 2. Extract user_id from event data and publish to Redis
        try:
            event_data = event_envelope.data

            # Use utility to extract user_id
            user_id = extract_user_id_from_event_data(event_data)

            if user_id:
                # Construct UI-friendly payload
                ui_payload = {
                    "timestamp": event_envelope.event_timestamp.isoformat(),
                    "correlation_id": extract_correlation_id_as_string(
                        event_envelope.correlation_id
                    ),
                }

                # Add event-specific data
                if hasattr(event_data, "class_id"):
                    ui_payload["class_id"] = event_data.class_id
                if hasattr(event_data, "class_designation"):
                    ui_payload["class_name"] = event_data.class_designation
                if hasattr(event_data, "student_id"):
                    ui_payload["student_id"] = event_data.student_id
                if hasattr(event_data, "first_name") and hasattr(event_data, "last_name"):
                    ui_payload["student_name"] = f"{event_data.first_name} {event_data.last_name}"

                # Determine event type for UI
                ui_event_type = getattr(event_data, "event", event_envelope.event_type)

                # Publish to Redis
                await self.redis_client.publish_user_notification(
                    user_id=user_id, event_type=ui_event_type, data=ui_payload
                )

                logger.info(
                    f"Published real-time notification to Redis channel for user {user_id}",
                    extra={"event_type": event_envelope.event_type, "user_id": user_id},
                )
            else:
                logger.warning(
                    "No user_id found in event data, skipping Redis publish",
                    extra={"event_type": event_envelope.event_type},
                )

        except Exception as e:
            logger.error(
                f"Error publishing to Redis: {e}",
                extra={"event_type": event_envelope.event_type},
                exc_info=True,
            )
            # Don't fail the entire event publishing if Redis fails
