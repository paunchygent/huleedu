"""Protocol definitions for BFF Teacher Service.

Defines interfaces for service clients used in dependency injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from services.bff_teacher_service.dto.teacher_v1 import (
        BatchSummaryV1,
        ClassInfoV1,
    )


class RASClientProtocol(Protocol):
    """Protocol for Result Aggregator Service HTTP client."""

    async def get_batches_for_user(
        self,
        user_id: str,
        correlation_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[BatchSummaryV1], dict]:
        """Get batches for a user with pagination.

        Args:
            user_id: User ID to query batches for
            correlation_id: Request correlation ID for tracing
            limit: Max batches to return (default 20)
            offset: Pagination offset (default 0)
            status: Optional internal status filter

        Returns:
            Tuple of (batches list, pagination dict with limit/offset/total)
        """
        ...


class CMSClientProtocol(Protocol):
    """Protocol for Class Management Service HTTP client."""

    async def get_class_info_for_batches(
        self,
        batch_ids: list[UUID],
        correlation_id: UUID,
    ) -> dict[str, ClassInfoV1 | None]:
        """Get class info for multiple batches.

        Args:
            batch_ids: List of batch UUIDs to lookup
            correlation_id: Request correlation ID for tracing

        Returns:
            Dict mapping batch_id (str) to ClassInfoV1 or None if no class
        """
        ...
