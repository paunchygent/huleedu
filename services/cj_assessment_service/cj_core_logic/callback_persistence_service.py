from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling import raise_cj_callback_correlation_failed
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_completion_policy import (
    BatchCompletionPolicy,
)
from services.cj_assessment_service.cj_core_logic.callback_retry_coordinator import (
    ComparisonRetryCoordinator,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
)

logger = create_service_logger("cj_assessment_service.callback_persistence_service")


class CallbackPersistenceService:
    """Persist callback updates and coordinate retry/completion side effects."""

    def __init__(
        self,
        *,
        completion_policy: BatchCompletionPolicy,
        retry_coordinator: ComparisonRetryCoordinator,
    ) -> None:
        self.completion_policy = completion_policy
        self.retry_coordinator = retry_coordinator

    async def update_comparison_result(
        self,
        *,
        comparison_result: Any,
        session: AsyncSession,
        comparison_repository: CJComparisonRepositoryProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        correlation_id: UUID,
        settings: Settings,
        pool_manager: Any | None = None,
        retry_processor: Any | None = None,
    ) -> int | None:
        comparison_pair = await comparison_repository.get_comparison_pair_by_correlation_id(
            session=session,
            correlation_id=correlation_id,
        )
        if comparison_pair is None:
            raise_cj_callback_correlation_failed(
                service="cj_assessment_service",
                operation="update_comparison_result",
                message=(
                    "Cannot find comparison pair for callback with correlation ID: "
                    f"{correlation_id}"
                ),
                correlation_id=correlation_id,
                callback_correlation_id=correlation_id,
            )

        if comparison_pair.winner is not None:
            logger.info(
                "Comparison pair %s already has result, skipping update",
                comparison_pair.id,
                extra={
                    "correlation_id": str(correlation_id),
                    "request_id": comparison_result.request_id,
                    "existing_winner": comparison_pair.winner,
                },
            )
            return comparison_pair.cj_batch_id

        comparison_pair.completed_at = comparison_result.completed_at
        if comparison_result.is_error and comparison_result.error_detail:
            self._apply_error_update(comparison_pair, comparison_result)
            if pool_manager and retry_processor and settings.ENABLE_FAILED_COMPARISON_RETRY:
                await self.retry_coordinator.add_failed_comparison_to_pool(
                    pool_manager=pool_manager,
                    retry_processor=retry_processor,
                    comparison_pair=comparison_pair,
                    comparison_result=comparison_result,
                    correlation_id=correlation_id,
                )
        else:
            if comparison_result.is_error:
                self._apply_malformed_error_update(
                    comparison_pair=comparison_pair,
                    comparison_result=comparison_result,
                    correlation_id=correlation_id,
                )
            else:
                self._apply_success_update(comparison_pair, comparison_result)
                if pool_manager and settings.ENABLE_FAILED_COMPARISON_RETRY:
                    await self.retry_coordinator.handle_successful_retry(
                        pool_manager=pool_manager,
                        comparison_pair=comparison_pair,
                        correlation_id=correlation_id,
                    )

        await self.completion_policy.update_batch_completion_counters(
            batch_repo=batch_repository,
            session=session,
            batch_id=comparison_pair.cj_batch_id,
            is_error=comparison_result.is_error,
            correlation_id=correlation_id,
        )
        await session.commit()
        return comparison_pair.cj_batch_id

    def _apply_error_update(self, comparison_pair: ComparisonPair, comparison_result: Any) -> None:
        comparison_pair.winner = "error"
        comparison_pair.error_code = comparison_result.error_detail.error_code.value
        comparison_pair.error_correlation_id = comparison_result.error_detail.correlation_id
        comparison_pair.error_timestamp = comparison_result.error_detail.timestamp
        comparison_pair.error_service = comparison_result.error_detail.service
        comparison_pair.error_details = comparison_result.error_detail.details
        logger.warning(
            "Updated comparison pair %s with error result",
            comparison_pair.id,
            extra={
                "error_code": comparison_result.error_detail.error_code.value,
                "error_provider": comparison_result.error_detail.details.get("provider")
                if comparison_result.error_detail.details
                else None,
            },
        )

    def _apply_success_update(
        self, comparison_pair: ComparisonPair, comparison_result: Any
    ) -> None:
        if comparison_result.winner:
            winner_value = comparison_result.winner.value
            comparison_pair.winner = winner_value.lower().replace(" ", "_")
        else:
            comparison_pair.winner = None

        comparison_pair.confidence = comparison_result.confidence
        comparison_pair.justification = comparison_result.justification
        comparison_pair.raw_llm_response = None
        comparison_pair.processing_metadata = {
            "provider": comparison_result.provider.value,
            "model": comparison_result.model,
            "response_time_ms": comparison_result.response_time_ms,
            "token_usage": {
                "prompt_tokens": comparison_result.token_usage.prompt_tokens,
                "completion_tokens": comparison_result.token_usage.completion_tokens,
                "total_tokens": comparison_result.token_usage.total_tokens,
            },
            "cost_estimate": comparison_result.cost_estimate,
        }
        logger.info(
            "Updated comparison pair %s with success result",
            comparison_pair.id,
            extra={
                "winner": comparison_pair.winner,
                "confidence": comparison_pair.confidence,
            },
        )

    def _apply_malformed_error_update(
        self,
        *,
        comparison_pair: ComparisonPair,
        comparison_result: Any,
        correlation_id: UUID,
    ) -> None:
        """Persist structurally malformed error callbacks without triggering retries."""

        comparison_pair.winner = "error"
        comparison_pair.error_code = ErrorCode.INVALID_RESPONSE.value
        comparison_pair.error_correlation_id = getattr(comparison_result, "correlation_id", None)
        comparison_pair.error_timestamp = getattr(comparison_result, "completed_at", None)
        comparison_pair.error_service = "llm_provider_service"
        comparison_pair.error_details = {
            "reason": "MALFORMED_CALLBACK_MISSING_ERROR_DETAIL",
        }
        logger.error(
            "Malformed error callback missing error_detail; persisted as INVALID_RESPONSE",
            extra={
                "correlation_id": str(correlation_id),
                "comparison_pair_id": comparison_pair.id,
                "batch_id": comparison_pair.cj_batch_id,
            },
        )
