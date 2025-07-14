"""Event publisher implementation for LLM usage events."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import get_current_span, inject_trace_context

from common_core import LLMProviderType
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import (
    LLMProviderFailureV1,
    LLMRequestCompletedV1,
    LLMRequestStartedV1,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMEventPublisherProtocol

logger = create_service_logger("llm_provider_service.event_publisher")


class LLMEventPublisherImpl(LLMEventPublisherProtocol):
    """Kafka-based event publisher for LLM usage events."""

    def __init__(self, kafka_bus: KafkaBus, settings: Settings):
        """Initialize event publisher.

        Args:
            kafka_bus: Kafka bus instance (with circuit breaker if enabled)
            settings: Service settings
        """
        self.kafka_bus = kafka_bus
        self.settings = settings

    def _str_to_provider_type(self, provider: str) -> LLMProviderType:
        """Convert string provider name to LLMProviderType enum."""
        try:
            return LLMProviderType(provider)
        except ValueError:
            logger.warning(f"Unknown provider '{provider}', defaulting to mock")
            return LLMProviderType.MOCK

    async def publish_llm_request_started(
        self,
        provider: str,
        correlation_id: UUID,
        metadata: Dict[str, Any],
    ) -> None:
        """Publish LLM request started event.

        Args:
            provider: LLM provider name
            correlation_id: Request correlation ID
            metadata: Additional event metadata
        """
        if not self.settings.PUBLISH_LLM_USAGE_EVENTS:
            return

        try:
            event_data = LLMRequestStartedV1(
                provider=self._str_to_provider_type(provider),
                request_type=metadata.get("request_type", "comparison"),
                correlation_id=correlation_id,
                user_id=metadata.get("user_id"),
                metadata=metadata,
            )

            envelope = EventEnvelope(
                event_type="llm_provider.request_started.v1",
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Inject trace context if we have an active span
            if get_current_span():
                if envelope.metadata is None:
                    envelope.metadata = {}
                inject_trace_context(envelope.metadata)

            topic = topic_name(ProcessingEvent.LLM_REQUEST_STARTED)
            await self.kafka_bus.publish(topic, envelope)

            logger.debug(
                f"Published LLM request started event for provider: {provider}, "
                f"correlation_id: {correlation_id}"
            )

        except Exception as e:
            # Log but don't fail the request due to event publishing failure
            logger.error(
                f"Failed to publish LLM request started event: {e}",
                exc_info=True,
                extra={"provider": provider, "correlation_id": str(correlation_id)},
            )

    async def publish_llm_request_completed(
        self,
        provider: str,
        correlation_id: UUID,
        success: bool,
        response_time_ms: int,
        metadata: Dict[str, Any],
    ) -> None:
        """Publish LLM request completed event.

        Args:
            provider: LLM provider name
            correlation_id: Request correlation ID
            success: Whether request was successful
            response_time_ms: Response time in milliseconds
            metadata: Additional event metadata
        """
        if not self.settings.PUBLISH_LLM_USAGE_EVENTS:
            return

        try:
            event_data = LLMRequestCompletedV1(
                provider=self._str_to_provider_type(provider),
                request_type=metadata.get("request_type", "comparison"),
                correlation_id=correlation_id,
                success=success,
                response_time_ms=response_time_ms,
                error_message=metadata.get("error_message"),
                token_usage=metadata.get("token_usage"),
                cost_estimate=metadata.get("cost_estimate"),
                metadata=metadata,
            )

            envelope = EventEnvelope(
                event_type="llm_provider.request_completed.v1",
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Inject trace context if we have an active span
            if get_current_span():
                if envelope.metadata is None:
                    envelope.metadata = {}
                inject_trace_context(envelope.metadata)

            topic = topic_name(ProcessingEvent.LLM_REQUEST_COMPLETED)
            await self.kafka_bus.publish(topic, envelope)

            logger.debug(
                f"Published LLM request completed event for provider: {provider}, "
                f"correlation_id: {correlation_id}, success: {success}"
            )

        except Exception as e:
            logger.error(
                f"Failed to publish LLM request completed event: {e}",
                exc_info=True,
                extra={
                    "provider": provider,
                    "correlation_id": str(correlation_id),
                    "success": success,
                },
            )

    async def publish_llm_provider_failure(
        self,
        provider: str,
        failure_type: str,
        correlation_id: UUID,
        error_details: str,
        circuit_breaker_opened: bool = False,
    ) -> None:
        """Publish LLM provider failure event.

        Args:
            provider: LLM provider name
            failure_type: Type of failure
            correlation_id: Request correlation ID
            error_details: Error details
            circuit_breaker_opened: Whether circuit breaker opened
        """
        if not self.settings.PUBLISH_LLM_USAGE_EVENTS:
            return

        try:
            event_data = LLMProviderFailureV1(
                provider=self._str_to_provider_type(provider),
                failure_type=failure_type,
                correlation_id=correlation_id,
                error_details=error_details,
                circuit_breaker_opened=circuit_breaker_opened,
                metadata={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            envelope = EventEnvelope(
                event_type="llm_provider.failure.v1",
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Inject trace context if we have an active span
            if get_current_span():
                if envelope.metadata is None:
                    envelope.metadata = {}
                inject_trace_context(envelope.metadata)

            topic = topic_name(ProcessingEvent.LLM_PROVIDER_FAILURE)
            await self.kafka_bus.publish(topic, envelope)

            logger.warning(
                f"Published LLM provider failure event for provider: {provider}, "
                f"failure_type: {failure_type}, correlation_id: {correlation_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to publish LLM provider failure event: {e}",
                exc_info=True,
                extra={
                    "provider": provider,
                    "correlation_id": str(correlation_id),
                    "failure_type": failure_type,
                },
            )

    async def publish_to_topic(
        self,
        topic: str,
        envelope: EventEnvelope[Any],
        key: Optional[str] = None,
    ) -> None:
        """Publish event to specific topic.

        Args:
            topic: Kafka topic name
            envelope: Event envelope to publish
            key: Optional message key for partitioning
        """
        try:
            # Use the existing kafka_bus.publish method for consistency
            await self.kafka_bus.publish(topic, envelope, key)

            logger.debug(
                f"Published event to topic: {topic}, "
                f"event_type: {envelope.event_type}, "
                f"correlation_id: {envelope.correlation_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to publish event to topic {topic}: {e}",
                exc_info=True,
                extra={
                    "topic": topic,
                    "event_type": envelope.event_type,
                    "correlation_id": str(envelope.correlation_id),
                },
            )
