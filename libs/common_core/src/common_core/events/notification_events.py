"""Teacher notification events for WebSocket delivery.

This module defines the unified notification event that all services emit
when they need to notify a teacher through the WebSocket service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory


class TeacherNotificationRequestedV1(BaseModel):
    """
    Universal teacher notification event.

    Services emit this event when they determine a teacher needs to be notified.
    The WebSocket service consumes ONLY these events, not internal domain events.

    Security: The emitting service MUST verify the teacher owns the related resources
    before emitting this event. WebSocket service trusts the teacher_id provided.
    """

    # Recipient
    teacher_id: str = Field(..., description="Teacher to notify (already authorized)")

    # Notification metadata
    notification_type: str = Field(..., description="One of the 15 defined notification types")
    category: WebSocketEventCategory = Field(..., description="UI category for grouping")
    priority: NotificationPriority = Field(..., description="Delivery priority")

    # Content
    payload: Dict[str, Any] = Field(..., description="Type-specific notification data")

    # Action tracking
    action_required: bool = Field(default=False, description="Teacher action needed")
    deadline_timestamp: Optional[datetime] = Field(None, description="Action deadline")

    # Correlation
    correlation_id: str = Field(..., description="Links to originating internal event")
    batch_id: Optional[str] = Field(None, description="Related batch if applicable")
    class_id: Optional[str] = Field(None, description="Related class if applicable")

    # Timestamp
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
