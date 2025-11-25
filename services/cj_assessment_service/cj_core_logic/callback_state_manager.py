"""Callback state management orchestrator for CJ Assessment Service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_completion_policy import (
    BatchCompletionPolicy,
)
from services.cj_assessment_service.cj_core_logic.callback_persistence_service import (
    CallbackPersistenceService,
)
from services.cj_assessment_service.cj_core_logic.callback_retry_coordinator import (
    ComparisonRetryCoordinator,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.callback_state_manager")

_completion_policy = BatchCompletionPolicy()
_retry_coordinator = ComparisonRetryCoordinator()
_persistence_service = CallbackPersistenceService(
    completion_policy=_completion_policy, retry_coordinator=_retry_coordinator
)


async def update_comparison_result(
    comparison_result: Any,
    session_provider: SessionProviderProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    correlation_id: UUID,
    settings: Settings,
    pool_manager: Any | None = None,
    retry_processor: Any | None = None,
) -> int | None:
    """Delegate comparison result persistence to the dedicated service.

    Args:
        comparison_result: LLM comparison result callback data
        session: Active database session for transaction
        comparison_repository: Repository for comparison pair operations
        batch_repository: Repository for batch operations
        correlation_id: Request correlation ID for tracing
        settings: Application settings
        pool_manager: Optional pool manager for retry coordination
        retry_processor: Optional retry processor for failed comparisons

    Returns:
        Batch ID if comparison pair found, None otherwise
    """
    async with session_provider.session() as session:
        return await _persistence_service.update_comparison_result(
            comparison_result=comparison_result,
            session=session,
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
            retry_processor=retry_processor,
        )


async def check_batch_completion_conditions(
    batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    correlation_id: UUID,
) -> bool:
    """Check completion heuristics using the shared completion policy.

    Args:
        batch_id: ID of the batch to check
        session: Active database session
        batch_repository: Repository for batch operations
        correlation_id: Request correlation ID for tracing

    Returns:
        True if batch meets completion conditions, False otherwise
    """
    async with session_provider.session() as session:
        return await _completion_policy.check_batch_completion_conditions(
            batch_id=batch_id,
            batch_repo=batch_repository,
            session=session,
            correlation_id=correlation_id,
        )


async def add_failed_comparison_to_pool(
    pool_manager: Any,
    retry_processor: Any,
    comparison_pair: ComparisonPair,
    comparison_result: Any,
    correlation_id: UUID,
) -> None:
    """Expose retry coordinator add-to-pool behavior for legacy callers."""

    await _retry_coordinator.add_failed_comparison_to_pool(
        pool_manager=pool_manager,
        retry_processor=retry_processor,
        comparison_pair=comparison_pair,
        comparison_result=comparison_result,
        correlation_id=correlation_id,
    )


async def reconstruct_comparison_task(
    comparison_pair: ComparisonPair, correlation_id: UUID
) -> ComparisonTask | None:
    """Proxy to retry coordinator reconstruction helper."""

    return await _retry_coordinator.reconstruct_comparison_task(
        comparison_pair=comparison_pair, correlation_id=correlation_id
    )


async def handle_successful_retry(
    pool_manager: Any, comparison_pair: ComparisonPair, correlation_id: UUID
) -> None:
    """Forward successful retry handling to the coordinator."""

    await _retry_coordinator.handle_successful_retry(
        pool_manager=pool_manager,
        comparison_pair=comparison_pair,
        correlation_id=correlation_id,
    )


async def _update_batch_completion_counters(
    session: AsyncSession,
    batch_repository: CJBatchRepositoryProtocol,
    batch_id: int,
    is_error: bool,
    correlation_id: UUID,
) -> None:
    """Compatibility wrapper for legacy tests referencing the private helper.

    Args:
        session: Active database session
        batch_repository: Repository for batch operations
        batch_id: ID of the batch to update
        is_error: Whether the comparison resulted in an error
        correlation_id: Request correlation ID for tracing
    """
    await _completion_policy.update_batch_completion_counters(
        batch_repo=batch_repository,
        session=session,
        batch_id=batch_id,
        is_error=is_error,
        correlation_id=correlation_id,
    )
