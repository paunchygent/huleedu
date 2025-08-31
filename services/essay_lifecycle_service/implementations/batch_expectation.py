"""
Batch expectation data structure for batch metadata.

Pure immutable data class containing batch registration information from BOS.
All state management and business logic has been moved to Redis coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from common_core.domain_enums import CourseCode


@dataclass(frozen=True)
class BatchExpectation:
    """
    Pure immutable data class for batch metadata.

    Contains only the batch registration information from BOS.
    NO business logic or mutable state - all operations handled by Redis coordinator.

    This is a value object representing the initial batch configuration.
    """

    batch_id: str
    expected_essay_ids: frozenset[str]  # Immutable set of internal essay ID slots from BOS
    expected_count: int
    course_code: CourseCode
    essay_instructions: str
    user_id: str
    org_id: str | None
    correlation_id: UUID  # Original correlation ID from registration
    created_at: datetime
    timeout_seconds: int = 86400  # 24 hours for complex processing including overnight LLM batches
