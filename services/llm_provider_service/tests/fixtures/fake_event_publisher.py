"""Fake event publisher for unit testing - records events without Kafka."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from common_core.events.envelope import EventEnvelope

from services.llm_provider_service.protocols import LLMEventPublisherProtocol


class FakeEventPublisher(LLMEventPublisherProtocol):
    """Records events for assertion without Kafka dependency."""

    def __init__(self) -> None:
        """Initialize fake event publisher."""
        self.published_events: List[Dict[str, Any]] = []

    async def publish_llm_request_started(
        self,
        provider: str,
        correlation_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record LLM request started event."""
        self.published_events.append(
            {
                "type": "llm_request_started",
                "provider": provider,
                "correlation_id": correlation_id,
                "metadata": metadata or {},
            }
        )

    async def publish_llm_request_completed(
        self,
        provider: str,
        correlation_id: UUID,
        success: bool,
        response_time_ms: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record LLM request completed event."""
        self.published_events.append(
            {
                "type": "llm_request_completed",
                "provider": provider,
                "correlation_id": correlation_id,
                "success": success,
                "response_time_ms": response_time_ms,
                "metadata": metadata or {},
            }
        )

    async def publish_llm_provider_failure(
        self,
        provider: str,
        failure_type: str,
        correlation_id: UUID,
        error_details: str,
        circuit_breaker_opened: bool = False,
        retry_count: Optional[int] = None,
    ) -> None:
        """Record LLM provider failure event."""
        self.published_events.append(
            {
                "type": "llm_provider_failure",
                "provider": provider,
                "failure_type": failure_type,
                "correlation_id": correlation_id,
                "error_details": error_details,
                "circuit_breaker_opened": circuit_breaker_opened,
                "retry_count": retry_count,
            }
        )

    async def publish_llm_comparison_result(
        self,
        provider: str,
        result: Dict[str, Any],
        correlation_id: UUID,
        callback_topic: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record LLM comparison result callback event."""
        self.published_events.append(
            {
                "type": "llm_comparison_result",
                "provider": provider,
                "result": result,
                "correlation_id": correlation_id,
                "callback_topic": callback_topic,
                "metadata": metadata or {},
            }
        )

    # Helper methods for test assertions

    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Get all events of a specific type."""
        return [event for event in self.published_events if event["type"] == event_type]

    def get_events_by_correlation_id(self, correlation_id: UUID) -> List[Dict[str, Any]]:
        """Get all events for a specific correlation ID."""
        return [
            event for event in self.published_events if event["correlation_id"] == correlation_id
        ]

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        """Get the most recently published event."""
        return self.published_events[-1] if self.published_events else None

    def get_last_event_of_type(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Get the most recent event of a specific type."""
        events = self.get_events_by_type(event_type)
        return events[-1] if events else None

    def has_event_type(self, event_type: str) -> bool:
        """Check if any event of the given type was published."""
        return any(event["type"] == event_type for event in self.published_events)

    def has_failure_event(self, correlation_id: UUID) -> bool:
        """Check if a failure event was published for the given correlation ID."""
        return any(
            event["type"] == "llm_provider_failure" and event["correlation_id"] == correlation_id
            for event in self.published_events
        )

    def has_success_event(self, correlation_id: UUID) -> bool:
        """Check if a successful completion event was published."""
        return any(
            event["type"] == "llm_request_completed"
            and event["correlation_id"] == correlation_id
            and event["success"] is True
            for event in self.published_events
        )

    def clear(self) -> None:
        """Clear all recorded events for test isolation."""
        self.published_events.clear()

    @property
    def event_count(self) -> int:
        """Get total number of published events."""
        return len(self.published_events)

    async def publish_to_topic(
        self,
        topic: str,
        envelope: EventEnvelope[Any],
        key: Optional[str] = None,
    ) -> None:
        """Record topic publication for testing."""
        self.published_events.append(
            {
                "type": "topic_publish",
                "topic": topic,
                "envelope": envelope,
                "key": key,
            }
        )

    def assert_event_published(
        self,
        event_type: str,
        correlation_id: Optional[UUID] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assert that a specific event was published and return it.

        Args:
            event_type: Type of event to check for
            correlation_id: Optional correlation ID to match
            provider: Optional provider to match

        Returns:
            The matching event

        Raises:
            AssertionError: If event was not found
        """
        matching_events = self.get_events_by_type(event_type)

        if correlation_id:
            matching_events = [e for e in matching_events if e["correlation_id"] == correlation_id]

        if provider:
            matching_events = [e for e in matching_events if e["provider"] == provider]

        if not matching_events:
            raise AssertionError(
                f"No {event_type} event found"
                f"{f' for correlation_id {correlation_id}' if correlation_id else ''}"
                f"{f' for provider {provider}' if provider else ''}"
            )

        return matching_events[0]
