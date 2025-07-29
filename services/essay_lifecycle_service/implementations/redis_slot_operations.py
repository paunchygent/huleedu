"""
Redis atomic slot assignment and return operations.

Handles the core business logic for atomic slot assignment and return
using Lua scripts to ensure consistency across distributed instances.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    from services.essay_lifecycle_service.implementations.redis_script_manager import (
        RedisScriptManager,
    )

logger = create_service_logger(__name__)


class RedisSlotOperations:
    """
    Handles atomic slot assignment and return operations using Redis Lua scripts.

    Provides idempotent slot assignment and safe slot return operations
    for distributed batch coordination.
    """

    def __init__(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> None:
        self._redis = redis_client
        self._script_manager = script_manager
        self._logger = logger

    async def assign_slot_atomic(
        self, batch_id: str, content_metadata: dict[str, Any], correlation_id: UUID | None = None
    ) -> str | None:
        """
        Atomically assign an available slot to content using a Lua script.

        This method is idempotent - calling it multiple times with the same
        text_storage_id will return the same essay_id without consuming additional slots.

        Args:
            batch_id: The batch identifier
            content_metadata: Content metadata including text_storage_id
            correlation_id: Optional correlation ID for error tracking

        Returns:
            The assigned essay ID if successful, None if no slots available

        Raises:
            HuleEduError: If content_metadata is invalid or Redis operation fails
        """
        text_storage_id = content_metadata.get("text_storage_id")
        if not text_storage_id:
            if correlation_id is None:
                correlation_id = UUID("00000000-0000-0000-0000-000000000000")
            error_detail = ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="content_metadata must include text_storage_id",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="essay_lifecycle_service",
                operation="assign_slot_atomic",
                details={"batch_id": batch_id, "content_metadata": content_metadata},
            )
            raise HuleEduError(error_detail)

        try:
            keys = [
                self._script_manager.get_content_assignments_key(batch_id),
                self._script_manager.get_available_slots_key(batch_id),
                self._script_manager.get_assignments_key(batch_id),
            ]
            args = [
                text_storage_id,
                json.dumps(content_metadata),
            ]

            result = await self._script_manager.execute_assign_script(keys, args)

            if result is None:
                self._logger.warning(
                    f"No available slots in batch {batch_id} for content {text_storage_id}"
                )
                return None

            # Validate that Redis returned a string essay_id
            if not isinstance(result, str):
                if correlation_id is None:
                    correlation_id = UUID("00000000-0000-0000-0000-000000000000")
                error_detail = ErrorDetail(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=(
                        f"Redis ATOMIC_ASSIGN_SCRIPT returned unexpected type: {type(result).__name__}. "
                        f"Expected string essay_id or None, got: {result!r}"
                    ),
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="essay_lifecycle_service",
                    operation="assign_slot_atomic",
                    details={
                        "batch_id": batch_id,
                        "text_storage_id": text_storage_id,
                        "returned_type": type(result).__name__,
                        "returned_value": str(result),
                    },
                )
                raise HuleEduError(error_detail)

            self._logger.info(
                f"Atomically assigned content {text_storage_id} to slot {result} "
                f"in batch {batch_id}"
            )
            return result

        except Exception as e:
            self._logger.error(
                f"Failed to assign slot for content {text_storage_id} in batch {batch_id}: {e}",
                exc_info=True,
            )
            raise

    async def return_slot(
        self, batch_id: str, text_storage_id: str, correlation_id: UUID | None = None
    ) -> bool:
        """
        Atomically return a previously assigned slot to the available pool.

        This is for POST-ASSIGNMENT rollback scenarios where a slot was
        successfully assigned but needs to be returned due to downstream
        processing failures.

        NOTE: This is NOT for pre-assignment validation failures, which
        are handled by track_validation_failure using SPOP.

        Args:
            batch_id: The batch identifier
            text_storage_id: The content ID whose slot should be returned
            correlation_id: Optional correlation ID for error tracking

        Returns:
            True if slot was returned, False if no assignment existed

        Raises:
            HuleEduError: If Redis operation fails
        """
        try:
            keys = [
                self._script_manager.get_content_assignments_key(batch_id),
                self._script_manager.get_available_slots_key(batch_id),
                self._script_manager.get_assignments_key(batch_id),
            ]
            args = [text_storage_id]

            result = await self._script_manager.execute_return_script(keys, args)

            # Script returns essay_id string if successful, None if no assignment found
            if result is None:
                self._logger.warning(
                    f"No slot assignment found for content {text_storage_id} in batch {batch_id}"
                )
                return False

            # Validate the returned essay_id
            if not isinstance(result, str):
                if correlation_id is None:
                    correlation_id = UUID("00000000-0000-0000-0000-000000000000")
                error_detail = ErrorDetail(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=(
                        f"Redis ATOMIC_RETURN_SCRIPT returned unexpected type: {type(result).__name__}. "
                        f"Expected string essay_id or None, got: {result!r}"
                    ),
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="essay_lifecycle_service",
                    operation="return_slot",
                    details={
                        "batch_id": batch_id,
                        "text_storage_id": text_storage_id,
                        "returned_type": type(result).__name__,
                        "returned_value": str(result),
                    },
                )
                raise HuleEduError(error_detail)

            self._logger.info(
                f"Returned slot {result} to batch {batch_id} for content {text_storage_id}"
            )
            return True

        except Exception as e:
            self._logger.error(
                f"Failed to return slot for content {text_storage_id} in batch {batch_id}: {e}",
                exc_info=True,
            )
            raise

    async def get_available_slot_count(self, batch_id: str) -> int:
        """
        Get the number of available slots remaining for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Number of available slots

        Raises:
            Exception: If Redis operation fails
        """
        try:
            slots_key = self._script_manager.get_available_slots_key(batch_id)
            return await self._redis.scard(slots_key)
        except Exception as e:
            self._logger.error(
                f"Failed to get available slot count for {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_assigned_count(self, batch_id: str) -> int:
        """
        Get count of assigned slots for a batch.

        Args:
            batch_id: The batch identifier

        Returns:
            Number of assigned slots

        Raises:
            Exception: If Redis operation fails
        """
        try:
            assignments_key = self._script_manager.get_assignments_key(batch_id)
            count = await self._redis.hlen(assignments_key)
            return count or 0

        except Exception as e:
            self._logger.error(
                f"Failed to get assigned count for batch {batch_id}: {e}", exc_info=True
            )
            raise

    async def get_essay_id_for_content(self, batch_id: str, text_storage_id: str) -> str | None:
        """
        Get the essay ID assigned to a specific text_storage_id.

        Args:
            batch_id: The batch identifier
            text_storage_id: The text storage ID to look up

        Returns:
            The essay ID if content is assigned, None otherwise

        Raises:
            Exception: If Redis operation fails
        """
        try:
            content_assignments_key = self._script_manager.get_content_assignments_key(batch_id)
            essay_id = await self._redis.hget(content_assignments_key, text_storage_id)
            return essay_id
        except Exception as e:
            self._logger.error(
                f"Failed to get essay ID for content {text_storage_id} in batch {batch_id}: {e}",
                exc_info=True,
            )
            raise
