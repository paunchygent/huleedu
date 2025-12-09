"""Teacher BFF API v1 routes.

Screen-specific endpoints for teacher dashboard. These routes aggregate data
from backend services (RAS, CMS) into frontend-optimized responses.

Stub implementation for scaffolding phase - full implementation will add:
- Dishka DI for service clients
- Backend service composition
- Error handling with structured errors
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from common_core.status_enums import BatchClientStatus
from fastapi import APIRouter

from services.bff_teacher_service.dto.teacher_v1 import (
    TeacherBatchItemV1,
    TeacherDashboardResponseV1,
)

router = APIRouter()


@router.get("/dashboard", response_model=TeacherDashboardResponseV1)
async def get_teacher_dashboard() -> TeacherDashboardResponseV1:
    """Get teacher dashboard: list of all batches with status and progress.

    Stub implementation returns sample data.
    Full implementation will aggregate data from:
    - Result Aggregator Service (batch statuses)
    - Class Management Service (class names)
    """
    # Mock data for initial scaffolding verification
    mock_regular_batch = TeacherBatchItemV1(
        batch_id=str(uuid4()),
        title="Hamlet Essay Assignment",
        class_name="Class 9A",
        status=BatchClientStatus.PROCESSING,
        total_essays=25,
        completed_essays=10,
        created_at=datetime.utcnow(),
    )

    mock_guest_batch = TeacherBatchItemV1(
        batch_id=str(uuid4()),
        title="Quick Assessment Demo",
        class_name=None,  # Guest batch has no class
        status=BatchClientStatus.COMPLETED_SUCCESSFULLY,
        total_essays=5,
        completed_essays=5,
        created_at=datetime.utcnow(),
    )

    return TeacherDashboardResponseV1(batches=[mock_regular_batch, mock_guest_batch], total_count=2)
