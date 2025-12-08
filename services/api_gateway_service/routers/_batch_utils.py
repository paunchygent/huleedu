"""Shared utilities and models for batch routes.

Private module containing shared constants, helpers, and Pydantic models
used across batch command, pipeline, and query routes.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from common_core.domain_enums import CourseCode
from common_core.events.client_commands import PipelinePromptPayload
from common_core.metadata_models import StorageReferenceMetadata
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger

from ..config import settings

logger = create_service_logger("api_gateway.batch_utils")


# Client-to-internal status mapping for filtering
# Each client status may map to multiple internal BatchStatus values
CLIENT_TO_INTERNAL_STATUS: dict[str, list[str]] = {
    "pending_content": ["awaiting_content_validation", "awaiting_pipeline_configuration"],
    "ready": ["ready_for_pipeline_execution"],
    "processing": [
        "processing_pipelines",
        "awaiting_student_validation",
        "student_validation_completed",
        "validation_timeout_processed",
    ],
    "completed_successfully": ["completed_successfully"],
    "completed_with_failures": ["completed_with_failures"],
    "failed": ["content_ingestion_failed", "failed_critically"],
    "cancelled": ["cancelled"],
}


def build_internal_auth_headers(correlation_id: UUID) -> dict[str, str]:
    """Build authentication headers for internal service calls.

    Args:
        correlation_id: Request correlation ID for tracing

    Returns:
        Headers dict with internal API key, service ID, and correlation ID
    """
    return {
        "X-Internal-API-Key": settings.get_internal_api_key(),
        "X-Service-ID": settings.SERVICE_NAME,
        "X-Correlation-ID": str(correlation_id),
    }


def map_internal_to_client_status(internal_status: str) -> str:
    """Map internal BatchStatus value to client-facing BatchClientStatus value.

    Args:
        internal_status: The internal status string from RAS

    Returns:
        Client-facing status string
    """
    for client_status, internal_statuses in CLIENT_TO_INTERNAL_STATUS.items():
        if internal_status in internal_statuses:
            return client_status

    logger.warning(f"Unknown internal status '{internal_status}', defaulting to 'pending_content'")
    return "pending_content"


# --- Request/Response Models ---


class BatchPipelineRequest(BaseModel):
    """Input model for batch pipeline requests from API Gateway clients.

    Separate from ClientBatchPipelineRequestV1 to avoid requiring
    user_id in the client request (it comes from authentication).
    """

    batch_id: str | None = Field(
        default=None,
        description="The unique identifier of the target batch (optional, taken from path).",
        min_length=1,
        max_length=255,
    )
    requested_pipeline: PhaseName = Field(
        description="The final pipeline phase the user wants to run."
    )
    is_retry: bool = Field(
        default=False,
        description="Flag indicating this is a user-initiated retry request.",
    )
    retry_reason: str | None = Field(
        default=None,
        description="Optional user-provided reason for the retry.",
        max_length=500,
    )
    prompt_payload: PipelinePromptPayload | None = Field(
        default=None,
        description="Prompt selection metadata: either canonical assignment_id or cms prompt reference.",
    )


class ClientBatchRegistrationRequest(BaseModel):
    """Client-facing registration model (no identity fields).

    API Gateway enriches this with `user_id` and optional `org_id` from JWT
    and forwards it to BOS using the shared inter-service contract.
    """

    expected_essay_count: int = Field(..., gt=0)
    essay_ids: list[str] | None = Field(default=None, min_length=1)
    course_code: CourseCode
    student_prompt_ref: StorageReferenceMetadata | None = None
    class_id: str | None = None
    cj_default_llm_model: str | None = None
    cj_default_temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class BatchListResponse(BaseModel):
    """Response model for batch listing."""

    batches: list[dict] = Field(..., description="List of batch summaries")
    pagination: dict = Field(..., description="Pagination metadata")
