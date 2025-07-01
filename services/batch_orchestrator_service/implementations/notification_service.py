"""Notification service for publishing pipeline phase updates to Redis."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("bos.notification.service")


class NotificationService:
    """Service for publishing real-time notifications about pipeline phase completions."""

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.redis_client = redis_client
        self.batch_repo = batch_repo

    async def publish_phase_completion(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: UUID,
    ) -> None:
        """
        Publish phase completion notification to Redis for real-time UI updates.

        Args:
            batch_id: The batch identifier
            completed_phase: The phase that was completed
            phase_status: The completion status of the phase
            correlation_id: Correlation ID for tracing
        """
        try:
            # Get batch context to extract user_id
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            user_id = batch_context.user_id if batch_context else None

            if user_id:
                await self.redis_client.publish_user_notification(
                    user_id=user_id,
                    event_type="batch_phase_concluded",
                    data={
                        "batch_id": batch_id,
                        "phase": completed_phase.value,
                        "status": phase_status.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "correlation_id": str(correlation_id),
                    },
                )

                logger.info(
                    f"Published phase completion notification to Redis for user {user_id}",
                    extra={
                        "batch_id": batch_id,
                        "phase": completed_phase.value,
                        "user_id": user_id,
                        "correlation_id": correlation_id,
                    },
                )
            else:
                logger.warning(
                    "No user_id found in batch context, skipping Redis notification",
                    extra={"batch_id": batch_id, "correlation_id": correlation_id},
                )

        except Exception as e:
            logger.error(
                f"Error publishing phase completion to Redis: {e}",
                extra={
                    "batch_id": batch_id,
                    "phase": completed_phase.value,
                    "correlation_id": correlation_id,
                },
                exc_info=True,
            )
            # Don't fail the entire phase handling if Redis fails
