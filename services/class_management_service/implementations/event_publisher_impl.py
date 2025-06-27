from huleedu_service_libs.kafka_client import KafkaBus

from common_core.events.envelope import EventEnvelope
from services.class_management_service.protocols import ClassEventPublisherProtocol


class DefaultClassEventPublisherImpl(ClassEventPublisherProtocol):
    """Default implementation of ClassEventPublisherProtocol using KafkaBus."""

    def __init__(self, kafka_bus: KafkaBus) -> None:
        self.kafka_bus = kafka_bus

    async def publish_class_event(self, event_envelope: EventEnvelope) -> None:
        topic = event_envelope.event_type
        await self.kafka_bus.publish(topic, event_envelope)
