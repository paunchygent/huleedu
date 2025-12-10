"""Teacher BFF API v1 routes.

Screen-specific endpoints for teacher dashboard. These routes aggregate data
from backend services (RAS, CMS) into frontend-optimized responses.
"""

from __future__ import annotations

from uuid import UUID

from common_core.status_enums import BatchClientStatus
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from httpx import ConnectError, ConnectTimeout, HTTPStatusError, ReadTimeout
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_external_service_error,
    raise_timeout_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.bff_teacher_service.dto.teacher_v1 import (
    TeacherBatchItemV1,
    TeacherDashboardResponseV1,
)
from services.bff_teacher_service.protocols import CMSClientProtocol, RASClientProtocol

router = APIRouter()
logger = create_service_logger("bff_teacher.teacher_routes")

# Status mapping: internal RAS status -> client-facing status
INTERNAL_TO_CLIENT_STATUS: dict[str, BatchClientStatus] = {
    "awaiting_content_validation": BatchClientStatus.PENDING_CONTENT,
    "awaiting_pipeline_configuration": BatchClientStatus.PENDING_CONTENT,
    "content_ingestion_failed": BatchClientStatus.FAILED,
    "ready_for_pipeline_execution": BatchClientStatus.READY,
    "processing_pipelines": BatchClientStatus.PROCESSING,
    "awaiting_student_validation": BatchClientStatus.PROCESSING,
    "student_validation_completed": BatchClientStatus.PROCESSING,
    "validation_timeout_processed": BatchClientStatus.PROCESSING,
    "completed_successfully": BatchClientStatus.COMPLETED_SUCCESSFULLY,
    "completed_with_failures": BatchClientStatus.COMPLETED_WITH_FAILURES,
    "failed_critically": BatchClientStatus.FAILED,
    "cancelled": BatchClientStatus.CANCELLED,
}


def map_to_client_status(internal_status: str) -> BatchClientStatus:
    """Map internal RAS status to client-facing status."""
    return INTERNAL_TO_CLIENT_STATUS.get(internal_status, BatchClientStatus.PENDING_CONTENT)


@router.get("/dashboard", response_model=TeacherDashboardResponseV1)
@inject
async def get_teacher_dashboard(
    ras_client: FromDishka[RASClientProtocol],
    cms_client: FromDishka[CMSClientProtocol],
    user_id: FromDishka[str],
    correlation_id: FromDishka[UUID],
) -> TeacherDashboardResponseV1:
    """Get teacher dashboard with batch list and class info.

    Aggregates data from RAS (batches) and CMS (class names).
    """
    try:
        # Get batches from RAS
        batches, pagination = await ras_client.get_batches_for_user(
            user_id=user_id,
            correlation_id=correlation_id,
            limit=100,
        )

        if not batches:
            return TeacherDashboardResponseV1(batches=[], total_count=0)

        # Get class info from CMS for all batches
        batch_ids = [UUID(b.batch_id) for b in batches]
        class_info_map = await cms_client.get_class_info_for_batches(
            batch_ids=batch_ids,
            correlation_id=correlation_id,
        )

        # Build response items
        items: list[TeacherBatchItemV1] = []
        for batch in batches:
            class_info = class_info_map.get(batch.batch_id)
            items.append(
                TeacherBatchItemV1(
                    batch_id=batch.batch_id,
                    title=batch.assignment_id or "Untitled Batch",
                    class_name=class_info.class_name if class_info else None,
                    status=map_to_client_status(batch.overall_status),
                    total_essays=batch.essay_count,
                    completed_essays=batch.completed_essay_count,
                    created_at=batch.created_at,
                )
            )

        return TeacherDashboardResponseV1(
            batches=items,
            total_count=pagination.get("total", len(items)),
        )

    except (ConnectTimeout, ReadTimeout) as e:
        logger.error(
            "Backend service timeout",
            extra={
                "error": str(e),
                "correlation_id": str(correlation_id),
            },
        )
        raise_timeout_error(
            service="bff_teacher_service",
            operation="get_teacher_dashboard",
            timeout_seconds=30.0,
            message="Backend service request timed out",
            correlation_id=correlation_id,
        )
    except ConnectError as e:
        logger.error(
            "Backend service connection error",
            extra={
                "error": str(e),
                "correlation_id": str(correlation_id),
            },
        )
        raise_connection_error(
            service="bff_teacher_service",
            operation="get_teacher_dashboard",
            target="backend_services",
            message="Failed to connect to backend service",
            correlation_id=correlation_id,
        )
    except HTTPStatusError as e:
        logger.error(
            "Backend service error",
            extra={
                "status_code": e.response.status_code,
                "correlation_id": str(correlation_id),
            },
        )
        raise_external_service_error(
            service="bff_teacher_service",
            operation="get_teacher_dashboard",
            external_service="backend",
            message="Failed to fetch dashboard data",
            correlation_id=correlation_id,
            status_code=e.response.status_code,
        )
