"""
Queue-related models for LLM Provider Service.

These models support the queue-based resilience pattern for handling
LLM requests during provider outages.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TypedDict
from uuid import UUID, uuid4

from common_core import LLMComparisonRequest, QueueStatus
from pydantic import BaseModel, ConfigDict, Field


class QueueHealthMetrics(TypedDict):
    """Type definition for queue health metrics."""

    type: str
    is_accepting: bool
    current_size: int
    max_size: int
    size_percent: float
    memory_usage_mb: float
    max_memory_mb: float
    memory_percent: float
    at_capacity: bool
    high_watermark: float
    low_watermark: float


class QueuedRequest(BaseModel):
    """Model for a queued LLM request."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        },
    )

    queue_id: UUID = Field(default_factory=uuid4, description="Unique queue identifier")
    request_data: LLMComparisonRequest = Field(description="Original request data")
    queued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When request was queued",
    )
    ttl: timedelta = Field(
        default=timedelta(hours=4),
        description="Time to live before expiration",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Priority level (0-10, higher = more urgent)",
    )
    status: QueueStatus = Field(
        default=QueueStatus.QUEUED,
        description="Current status of the request",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of processing attempts",
    )
    size_bytes: int = Field(
        ge=0,
        description="Serialized size in bytes for memory tracking",
    )

    # Optional tracking fields
    processing_started_at: Optional[datetime] = Field(
        default=None,
        description="When processing began",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When processing completed",
    )
    message: Optional[str] = Field(
        default=None,
        description="Error details if failed",
    )
    result_location: Optional[str] = Field(
        default=None,
        description="Where to find the completed result",
    )

    # Metadata for client context
    correlation_id: Optional[UUID] = Field(
        default=None,
        description="Client-provided correlation ID",
    )
    callback_topic: str = Field(..., description="Kafka topic for result delivery")
    trace_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="OpenTelemetry trace context for request processing",
    )

    def is_expired(self) -> bool:
        """Check if the request has expired based on TTL."""
        return datetime.now(timezone.utc) > self.queued_at + self.ttl

    def calculate_size(self) -> int:
        """Calculate the serialized size of this request."""
        return len(self.model_dump_json())

    def __lt__(self, other: "QueuedRequest") -> bool:
        """Compare requests for heap ordering (higher priority first, then FIFO)."""
        if not isinstance(other, QueuedRequest):
            return False

        # Higher priority comes first (reverse order for min-heap)
        if self.priority != other.priority:
            return self.priority > other.priority

        # For same priority, earlier queued time comes first
        return self.queued_at < other.queued_at

    def __eq__(self, other: object) -> bool:
        """Check equality based on queue_id."""
        if not isinstance(other, QueuedRequest):
            return False
        return self.queue_id == other.queue_id


class QueueStats(BaseModel):
    """Statistics about the current queue state."""

    model_config = ConfigDict(str_strip_whitespace=True)

    current_size: int = Field(ge=0, description="Number of items in queue")
    max_size: int = Field(gt=0, description="Maximum queue capacity")
    memory_usage_mb: float = Field(ge=0.0, description="Current memory usage in MB")
    max_memory_mb: float = Field(gt=0.0, description="Maximum memory allowed in MB")
    usage_percent: float = Field(ge=0.0, le=100.0, description="Percentage of capacity used")
    oldest_item_age_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="Age of oldest queued item in seconds",
    )
    processing_rate_per_minute: float = Field(
        ge=0.0,
        default=0.0,
        description="Average processing rate",
    )
    estimated_wait_minutes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Estimated wait time for new requests",
    )

    # Breakdown by status
    queued_count: int = Field(default=0, ge=0)
    processing_count: int = Field(default=0, ge=0)
    completed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)

    # Health indicators
    is_accepting_requests: bool = Field(
        default=True,
        description="Whether queue is accepting new requests",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Why requests are being rejected",
    )


class QueueFullError(BaseModel):
    """Error response when queue is at capacity."""

    model_config = ConfigDict(str_strip_whitespace=True)

    error: str = Field(default="Queue at capacity")
    queue_stats: Dict[str, Any] = Field(
        description="Current queue statistics",
        default_factory=lambda: {
            "current_size": 0,
            "max_size": 1000,
            "usage_percent": 0.0,
            "estimated_wait_hours": "2-4",
            "retry_after_seconds": 300,
        },
    )
    status_code: int = Field(default=503)
    retry_after: int = Field(
        default=300,
        description="Seconds before client should retry",
    )


class QueueStatusResponse(BaseModel):
    """Response for queue status queries."""

    model_config = ConfigDict(str_strip_whitespace=True)

    queue_id: UUID
    status: QueueStatus
    queued_at: datetime
    position_in_queue: Optional[int] = None
    estimated_processing_time: Optional[timedelta] = None
    result_available: bool = False
    result_location: Optional[str] = None
    message: Optional[str] = None
    expires_at: datetime
