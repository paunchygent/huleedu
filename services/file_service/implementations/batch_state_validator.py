"""Batch state validation implementation for File Service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import aiohttp
from common_core.pipeline_models import PipelineExecutionStatus, ProcessingPipelineState
from huleedu_service_libs.error_handling import (
    raise_authorization_error,
    raise_external_service_error,
    raise_invalid_response,
    raise_processing_error,
    raise_resource_not_found,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.config import Settings

logger = create_service_logger("file_service.batch_state_validator")


class BOSBatchStateValidator:
    """Validates batch state by querying BOS for pipeline status."""

    def __init__(self, http_session: aiohttp.ClientSession, settings: Settings) -> None:
        self.http_session = http_session
        self.settings = settings

    async def _fetch_json(self, url: str) -> tuple[int, Any]:
        """Perform GET request and return (status, json). Ensures response released."""
        request_obj = self.http_session.get(url, timeout=aiohttp.ClientTimeout(total=5))

        # Support both aiohttp style (await) and tests using async context manager mocks
        if hasattr(request_obj, "__aenter__"):
            async with request_obj as resp:
                status_code = resp.status
                data = await resp.json()
                return status_code, data
        else:
            resp = await request_obj
            try:
                status_code = resp.status
                data = await resp.json()
                return status_code, data
            finally:
                resp.release()

    async def can_modify_batch_files(
        self, batch_id: str, user_id: str, correlation_id: UUID
    ) -> None:
        """
        Check if batch files can be modified by querying BOS pipeline state.

        Files cannot be modified if:
        - Any processing phase has active status (DISPATCH_INITIATED, IN_PROGRESS, or completed)
        - User doesn't own the batch
        - Batch doesn't exist

        Args:
            batch_id: The batch identifier
            user_id: The authenticated user identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            None if modification is allowed

        Raises:
            HuleEduError: If batch cannot be modified with specific reason
        """
        try:
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"

            status, pipeline_data = await self._fetch_json(bos_url)
            if status == 404:
                raise_resource_not_found(
                    service="file_service",
                    operation="can_modify_batch_files",
                    resource_type="batch",
                    resource_id=batch_id,
                    correlation_id=correlation_id,
                )
            elif status != 200:
                logger.error(f"BOS query failed for batch {batch_id}: status {status}")
                raise_external_service_error(
                    service="file_service",
                    operation="can_modify_batch_files",
                    external_service="batch_orchestrator_service",
                    message=f"External service error: Failed to verify batch state (HTTP {status})",
                    correlation_id=correlation_id,
                    status_code=status,
                )

            # Verify user ownership
            batch_user_id = pipeline_data.get("user_id")
            if batch_user_id != user_id:
                raise_authorization_error(
                    service="file_service",
                    operation="can_modify_batch_files",
                    message="You don't own this batch",
                    correlation_id=correlation_id,
                    batch_owner=batch_user_id,
                    requested_user=user_id,
                    batch_id=batch_id,
                )

            # Parse pipeline state using Pydantic model for type safety
            pipeline_state_data = pipeline_data.get("pipeline_state", {})

            try:
                pipeline_state = ProcessingPipelineState.model_validate(pipeline_state_data)
            except Exception as e:
                logger.error(
                    f"Failed to parse pipeline state for batch {batch_id}: {e}",
                    exc_info=True,
                )
                raise_invalid_response(
                    service="file_service",
                    operation="can_modify_batch_files",
                    message="Invalid pipeline state format from BOS",
                    correlation_id=correlation_id,
                    parse_error=str(e),
                )

            # Check each phase for locking status using proper enum values
            self._check_pipeline_state(pipeline_state, batch_id, correlation_id)

        except HuleEduError:
            # Re-raise HuleEduError as-is without wrapping
            raise
        except (aiohttp.ClientError, Exception) as e:
            # Network and HTTP errors should be treated as external service errors
            logger.error(f"Error validating batch state for {batch_id}: {e}", exc_info=True)
            raise_external_service_error(
                service="file_service",
                operation="can_modify_batch_files",
                external_service="batch_orchestrator_service",
                message="Failed to communicate with external service",
                correlation_id=correlation_id,
                error=str(e),
            )

    def _check_pipeline_state(
        self, pipeline_state: ProcessingPipelineState, batch_id: str, correlation_id: UUID
    ) -> None:
        """
        Check pipeline state using Pydantic model with proper enum values.

        Args:
            pipeline_state: The pipeline state to check
            batch_id: The batch identifier for error context
            correlation_id: Request correlation ID for tracing

        Returns:
            None if batch can be modified

        Raises:
            HuleEduError: If batch is locked due to active processing
        """
        # Define statuses that indicate active processing (batch is locked)
        locking_statuses = {
            PipelineExecutionStatus.DISPATCH_INITIATED,
            PipelineExecutionStatus.IN_PROGRESS,
            PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
            PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS,
        }

        # Check all phases for locking status
        phases_to_check = [
            ("spellcheck", pipeline_state.spellcheck),
            ("ai_feedback", pipeline_state.ai_feedback),
            ("cj_assessment", pipeline_state.cj_assessment),
            ("nlp_metrics", pipeline_state.nlp_metrics),
        ]

        for phase_name, phase_detail in phases_to_check:
            if phase_detail and phase_detail.status in locking_statuses:
                raise_processing_error(
                    service="file_service",
                    operation="can_modify_batch_files",
                    message=f"Batch {batch_id} is locked: {phase_name} processing has started",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    locked_by_phase=phase_name,
                    phase_status=phase_detail.status.value,
                )

        # No exception raised means batch can be modified

    async def get_batch_lock_status(self, batch_id: str, correlation_id: UUID) -> dict[str, Any]:
        """
        Get detailed batch lock status for client information.

        Args:
            batch_id: The batch identifier
            correlation_id: Request correlation ID for tracing

        Returns:
            dict: Lock status with reason and metadata

        Raises:
            HuleEduError: If batch status cannot be retrieved
        """
        try:
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"

            status, pipeline_data = await self._fetch_json(bos_url)
            if status != 200:
                return {
                    "locked": True,
                    "reason": "Unable to verify batch state",
                    "status_code": status,
                }

            pipeline_state_data = pipeline_data.get("pipeline_state", {})

            # Use Pydantic model for type safety - no fallback
            try:
                pipeline_state = ProcessingPipelineState.model_validate(pipeline_state_data)
                return self._get_lock_status(pipeline_state)
            except Exception as e:
                logger.error(
                    f"Failed to parse pipeline state for batch {batch_id}: {e}",
                    exc_info=True,
                )
                return {"locked": True, "reason": "Invalid pipeline state format"}

        except Exception as e:
            logger.error(f"Error getting batch lock status for {batch_id}: {e}", exc_info=True)
            return {"locked": True, "reason": "Unable to verify batch state"}

    def _get_lock_status(self, pipeline_state: ProcessingPipelineState) -> dict[str, Any]:
        """Get lock status using Pydantic model with proper enum values."""
        locking_statuses = {
            PipelineExecutionStatus.DISPATCH_INITIATED,
            PipelineExecutionStatus.IN_PROGRESS,
            PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
            PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS,
        }

        phases_to_check = [
            ("spellcheck", pipeline_state.spellcheck),
            ("ai_feedback", pipeline_state.ai_feedback),
            ("cj_assessment", pipeline_state.cj_assessment),
            ("nlp_metrics", pipeline_state.nlp_metrics),
        ]

        for phase_name, phase_detail in phases_to_check:
            if phase_detail and phase_detail.status in locking_statuses:
                return {
                    "locked": True,
                    "reason": f"{phase_name} processing has started",
                    "locked_at": (
                        phase_detail.started_at.isoformat() if phase_detail.started_at else None
                    ),
                    "current_phase": phase_name,
                    "phase_status": phase_detail.status.value,
                }

        return {
            "locked": False,
            "reason": "Batch is open for modifications",
            "current_state": "READY_FOR_MODIFICATIONS",
        }
