"""Teacher BFF API v1 routes.

Screen-specific endpoints for teacher dashboard. These routes aggregate data
from backend services (RAS, CMS) into frontend-optimized responses.

Stub implementation for scaffolding phase - full implementation will add:
- Dishka DI for service clients
- Backend service composition
- Error handling with structured errors
"""

from __future__ import annotations

from fastapi import APIRouter

from services.bff_teacher_service.dto.teacher_v1 import TeacherDashboardResponseV1

router = APIRouter()


@router.get("/dashboard", response_model=TeacherDashboardResponseV1)
async def get_teacher_dashboard() -> TeacherDashboardResponseV1:
    """Get teacher dashboard: list of all batches with status and progress.

    Stub implementation returns empty dashboard.
    Full implementation will aggregate data from:
    - Result Aggregator Service (batch statuses)
    - Class Management Service (class names)
    """
    return TeacherDashboardResponseV1(batches=[], total_count=0)
