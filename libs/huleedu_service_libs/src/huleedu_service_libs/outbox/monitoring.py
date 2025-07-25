"""
Prometheus metrics for the Transactional Outbox Pattern.

This module provides standardized metrics for monitoring the health and performance
of the outbox pattern across all implementing services.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Gauge for current queue depth (unpublished events)
outbox_queue_depth = Gauge(
    "outbox_queue_depth",
    "Number of unpublished events currently in the outbox",
    ["service"],
)

# Counter for total events added to outbox
outbox_events_added_total = Counter(
    "outbox_events_added_total",
    "Total number of events added to the outbox",
    ["service", "event_type"],
)

# Counter for successfully published events
outbox_events_published_total = Counter(
    "outbox_events_published_total",
    "Total number of events successfully published from outbox",
    ["service", "event_type"],
)

# Counter for permanently failed events (exceeded max retries)
outbox_events_failed_total = Counter(
    "outbox_events_failed_total",
    "Total number of events that permanently failed (exceeded max retries)",
    ["service", "event_type"],
)

# Counter for relay errors (temporary failures)
outbox_relay_errors_total = Counter(
    "outbox_relay_errors_total",
    "Total number of errors encountered by the relay worker",
    ["service", "error_type"],
)

# Histogram for event age (time from creation to publication)
outbox_event_age_seconds = Histogram(
    "outbox_event_age_seconds",
    "Age of events when published (seconds from creation to publication)",
    ["service"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 3600.0),
)

# Histogram for relay processing time
outbox_relay_processing_seconds = Histogram(
    "outbox_relay_processing_seconds",
    "Time taken to process and publish an event from outbox",
    ["service"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)


class OutboxMetrics:
    """
    Helper class for updating outbox metrics.

    This class provides convenient methods for updating Prometheus metrics
    related to the outbox pattern, with proper labeling by service.
    """

    def __init__(self, service_name: str = "unknown") -> None:
        """
        Initialize metrics helper.

        Args:
            service_name: Name of the service for metric labels
        """
        self.service_name = service_name

    def increment_events_added(self, event_type: str) -> None:
        """Increment counter for events added to outbox."""
        outbox_events_added_total.labels(
            service=self.service_name,
            event_type=event_type,
        ).inc()

    def increment_published_events(self, event_type: str | None = None) -> None:
        """Increment counter for successfully published events."""
        outbox_events_published_total.labels(
            service=self.service_name,
            event_type=event_type or "unknown",
        ).inc()

    def increment_failed_events(self, event_type: str | None = None) -> None:
        """Increment counter for permanently failed events."""
        outbox_events_failed_total.labels(
            service=self.service_name,
            event_type=event_type or "unknown",
        ).inc()

    def increment_errors(self, error_type: str = "generic") -> None:
        """Increment counter for relay errors."""
        outbox_relay_errors_total.labels(
            service=self.service_name,
            error_type=error_type,
        ).inc()

    def set_queue_depth(self, depth: int) -> None:
        """Set the current queue depth gauge."""
        outbox_queue_depth.labels(service=self.service_name).set(depth)

    def observe_event_age(self, age_seconds: float) -> None:
        """Record the age of a published event."""
        outbox_event_age_seconds.labels(service=self.service_name).observe(age_seconds)

    def observe_processing_time(self, duration_seconds: float) -> None:
        """Record the processing time for an event."""
        outbox_relay_processing_seconds.labels(service=self.service_name).observe(
            duration_seconds
        )