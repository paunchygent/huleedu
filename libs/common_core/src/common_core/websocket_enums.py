"""WebSocket service enums for event categorization and notification handling."""

from __future__ import annotations

from enum import Enum


class WebSocketEventCategory(str, Enum):
    """Categories for WebSocket event prioritization and filtering."""

    BATCH_PROGRESS = "batch_progress"  # Batch processing updates
    PROCESSING_RESULTS = "processing_results"  # Service completion events
    FILE_OPERATIONS = "file_operations"  # File upload/removal events
    CLASS_MANAGEMENT = "class_management"  # Class/student operations
    STUDENT_WORKFLOW = "student_workflow"  # Student matching/validation
    SYSTEM_ALERTS = "system_alerts"  # Error notifications


class NotificationPriority(str, Enum):
    """
    Notification priority levels for teacher notifications.

    Priority determines delivery urgency and UI presentation.
    """

    CRITICAL = "critical"  # Requires action within 24 hours (deadline approaching)
    IMMEDIATE = "immediate"  # Requires prompt attention (errors, failures)
    HIGH = "high"  # Important but not urgent (processing complete)
    STANDARD = "standard"  # Normal priority (progress updates)
    LOW = "low"  # Informational only (status changes)


class WebSocketConnectionState(str, Enum):
    """WebSocket connection lifecycle states."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DISCONNECTED = "disconnected"
    ERROR = "error"
