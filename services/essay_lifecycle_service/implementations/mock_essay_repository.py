"""
Mock repository implementation for Essay Lifecycle Service.

This provides a fast, in-memory implementation of EssayRepositoryProtocol
for unit testing with comprehensive constraint simulation and atomic
operation support matching PostgreSQL behavior.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.constants import ELS_PHASE_STATUS_MAPPING
from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState as ProtocolEssayState


class MockEssayRepository(EssayRepositoryProtocol):
    """
    Mock implementation with full PostgreSQL behavior simulation.

    This implementation provides:
    - Full EssayRepositoryProtocol compliance
    - Comprehensive constraint simulation matching PostgreSQL
    - Enhanced atomic operation support with asyncio locks
    - Production-like behavior patterns for reliable unit testing

    Key Features:
    - Simulates PostgreSQL's partial unique index on (batch_id, text_storage_id)
    - Uses asyncio.Lock for atomic operation simulation
    - Includes phase status mapping identical to PostgreSQL implementation
    - Proper session parameter handling (ignored but acknowledged)
    """

    def __init__(self) -> None:
        """Initialize the mock repository with internal storage and atomic operation support."""
        # Core storage
        self.essays: dict[str, EssayState] = {}

        # Constraint simulation (mimics PostgreSQL unique indexes)
        # Only enforces uniqueness when text_storage_id is not None
        self._unique_constraints: dict[
            tuple[str, str], str
        ] = {}  # (batch_id, text_storage_id) -> essay_id

        # Atomicity simulation using asyncio locks
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()  # For operations affecting multiple entities

        # Session factory mock (returns None as we don't use real sessions)
        self._session_factory = None

        # Logging
        self.logger = create_service_logger("els.repository.mock")

        self.logger.info("MockEssayRepository initialized")

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific resource (simulates row-level locking)."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        return self.essays.get(essay_id)

    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """
        Update essay state with new status and metadata.

        Note: Mock implementation ignores session parameter as it uses in-memory storage.
        """
        _ = session  # Explicitly ignore for protocol compliance

        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            correlation_id = uuid4()

        async with self._get_lock(essay_id):
            essay = self.essays.get(essay_id)
            if not essay:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_state",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            # Update using domain model method
            essay.update_status(new_status, metadata)

            # Handle storage reference if provided
            if storage_reference:
                content_type, storage_id = storage_reference
                essay.add_storage_reference(content_type, storage_id)

    async def update_essay_status_via_machine(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state using status from state machine."""
        # For mock implementation, this behaves identically to update_essay_state
        await self.update_essay_state(
            essay_id, new_status, metadata, session, storage_reference, correlation_id
        )

    async def create_essay_record(
        self,
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> EssayState:
        """Create new essay record from primitive parameters."""
        _ = session  # Explicitly ignore for protocol compliance

        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            correlation_id = uuid4()

        async with self._get_lock(essay_id):
            # Check if essay already exists
            if essay_id in self.essays:
                raise_validation_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_record",
                    field="essay_id",
                    message=f"Essay with ID {essay_id} already exists",
                    correlation_id=correlation_id,
                    value=essay_id,
                )

            # Create new essay state
            essay_state = EssayState(
                essay_id=essay_id,
                batch_id=batch_id,
                current_status=EssayStatus.UPLOADED,
                processing_metadata={
                    "entity_type": entity_type,
                    "created_via": "create_essay_record",
                },
                timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
            )

            # Store essay
            self.essays[essay_id] = essay_state

            self.logger.info(f"Created essay record {essay_id} in batch {batch_id}")
            return essay_state

    async def create_essay_records_batch(
        self,
        essay_data: list[dict[str, str | None]],
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> list[ProtocolEssayState]:
        """Create multiple essay records in single atomic transaction."""
        _ = session  # Explicitly ignore for protocol compliance

        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            correlation_id = uuid4()

        # Use global lock for batch operations
        async with self._global_lock:
            created_essays: list[ProtocolEssayState] = []

            # Validate all essay_ids are unique first
            essay_ids = [data.get("essay_id") for data in essay_data]
            if not all(essay_ids):
                raise_validation_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_records_batch",
                    field="essay_id",
                    message="All essay records must have essay_id",
                    correlation_id=correlation_id,
                )

            # Check for duplicates within the batch
            if len(set(essay_ids)) != len(essay_ids):
                raise_validation_error(
                    service="essay_lifecycle_service",
                    operation="create_essay_records_batch",
                    field="essay_id",
                    message="Duplicate essay_ids in batch",
                    correlation_id=correlation_id,
                )

            # Check for existing essays
            for essay_id in essay_ids:
                if essay_id in self.essays:
                    raise_validation_error(
                        service="essay_lifecycle_service",
                        operation="create_essay_records_batch",
                        field="essay_id",
                        message=f"Essay with ID {essay_id} already exists",
                        correlation_id=correlation_id,
                        value=essay_id,
                    )

            # Create all essays
            for data in essay_data:
                essay_id = data["essay_id"]
                if essay_id is None:
                    raise_validation_error(
                        service="essay_lifecycle_service",
                        operation="create_essay_records_batch",
                        field="essay_id",
                        message="essay_id cannot be None",
                        correlation_id=correlation_id,
                    )

                batch_id = data.get("batch_id")
                entity_type = data.get("entity_type", "essay")

                essay_state = EssayState(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    current_status=EssayStatus.UPLOADED,
                    processing_metadata={
                        "entity_type": entity_type,
                        "created_via": "create_essay_records_batch",
                    },
                    timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
                )

                self.essays[essay_id] = essay_state
                created_essays.append(essay_state)

            self.logger.info(f"Created {len(created_essays)} essay records in batch")
            return created_essays

    async def list_essays_by_batch(self, batch_id: str) -> list[ProtocolEssayState]:
        """List all essays in a batch."""
        return [essay for essay in self.essays.values() if essay.batch_id == batch_id]

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch."""
        status_counts: dict[EssayStatus, int] = {}

        for essay in self.essays.values():
            if essay.batch_id == batch_id:
                status = essay.current_status
                status_counts[status] = status_counts.get(status, 0) + 1

        return status_counts

    async def get_batch_summary_with_essays(
        self, batch_id: str
    ) -> tuple[list[ProtocolEssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation."""
        essays = await self.list_essays_by_batch(batch_id)
        status_summary = await self.get_batch_status_summary(batch_id)
        return essays, status_summary

    async def get_essay_by_text_storage_id_and_batch_id(
        self, batch_id: str, text_storage_id: str
    ) -> EssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        for essay in self.essays.values():
            if (
                essay.batch_id == batch_id
                and essay.storage_references.get(ContentType.ORIGINAL_ESSAY) == text_storage_id
            ):
                return essay
        return None

    async def create_or_update_essay_state_for_slot_assignment(
        self,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> EssayState:
        """Create or update essay state for slot assignment with content metadata."""
        _ = session  # Explicitly ignore for protocol compliance

        # Generate correlation_id if not provided for error handling
        if correlation_id is None:
            correlation_id = uuid4()

        async with self._get_lock(internal_essay_id):
            existing_essay = await self.get_essay_state(internal_essay_id)

            if existing_essay is not None:
                # Update existing essay with new metadata
                metadata_updates = {
                    "text_storage_id": text_storage_id,
                    "original_file_name": original_file_name,
                    "file_size": file_size,
                    "content_hash": content_hash,
                    "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                }

                existing_essay.processing_metadata.update(metadata_updates)
                existing_essay.add_storage_reference(ContentType.ORIGINAL_ESSAY, text_storage_id)
                existing_essay.current_status = initial_status
                existing_essay.batch_id = batch_id
                existing_essay.text_storage_id = text_storage_id
                existing_essay.updated_at = datetime.now(UTC)

                self.logger.info(f"Updated essay {internal_essay_id} for slot assignment")
                return existing_essay
            else:
                # Create new essay state
                essay_state = EssayState(
                    essay_id=internal_essay_id,
                    batch_id=batch_id,
                    current_status=initial_status,
                    processing_metadata={
                        "text_storage_id": text_storage_id,
                        "original_file_name": original_file_name,
                        "file_size": file_size,
                        "content_hash": content_hash,
                        "slot_assignment_timestamp": datetime.now(UTC).isoformat(),
                    },
                    storage_references={ContentType.ORIGINAL_ESSAY: text_storage_id},
                    timeline={initial_status.value: datetime.now(UTC)},
                    text_storage_id=text_storage_id,
                )

                self.essays[internal_essay_id] = essay_state

                self.logger.info(f"Created essay {internal_essay_id} for slot assignment")
                return essay_state

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str, session: AsyncSession | None = None
    ) -> list[ProtocolEssayState]:
        """
        List all essays in a batch that are part of a specific processing phase.

        Must match PostgreSQL's phase logic exactly.
        """
        _ = session  # Explicitly ignore for protocol compliance

        # Convert string phase name to PhaseName enum for lookup
        try:
            from common_core.pipeline_models import PhaseName

            phase_enum = PhaseName(phase_name) if isinstance(phase_name, str) else phase_name
            phase_statuses = ELS_PHASE_STATUS_MAPPING.get(phase_enum, [])
        except (ValueError, KeyError):
            phase_statuses = []
        if not phase_statuses:
            self.logger.warning(f"Unknown phase: {phase_name}")
            return []

        return [
            essay
            for essay in self.essays.values()
            if essay.batch_id == batch_id and essay.current_status in phase_statuses
        ]

    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> tuple[bool, str | None]:
        """
        Create essay state with atomic idempotency check for content provisioning.

        Simulates PostgreSQL's partial unique index on (batch_id, text_storage_id).
        Only enforces uniqueness when text_storage_id is not None.

        Returns tuple of (was_created, essay_id) where was_created indicates if this
        was a new creation (True) or idempotent case (False).
        """
        _ = session  # Explicitly ignore for protocol compliance

        constraint_key = (batch_id, text_storage_id) if text_storage_id else None

        # First check without lock (fast path)
        if constraint_key and constraint_key in self._unique_constraints:
            existing_essay_id = self._unique_constraints[constraint_key]
            return (False, existing_essay_id)

        # Atomic creation with constraint registration
        async with self._get_lock(f"{batch_id}:{text_storage_id}"):
            # Double-check inside lock (prevents race conditions)
            if constraint_key and constraint_key in self._unique_constraints:
                existing_essay_id = self._unique_constraints[constraint_key]
                return (False, existing_essay_id)

            # Create essay
            essay_id = essay_data.get("internal_essay_id", str(uuid4()))

            essay = EssayState(
                essay_id=essay_id,
                batch_id=batch_id,
                current_status=EssayStatus(
                    essay_data.get("initial_status", EssayStatus.UPLOADED.value)
                ),
                text_storage_id=text_storage_id,
                processing_metadata={
                    "original_file_name": essay_data.get("original_file_name", ""),
                    "file_size_bytes": essay_data.get("file_size", 0),
                    "content_md5_hash": essay_data.get("content_hash", ""),
                    "created_via": "create_essay_state_with_content_idempotency",
                },
                storage_references={ContentType.ORIGINAL_ESSAY: text_storage_id},
                timeline={EssayStatus.UPLOADED.value: datetime.now(UTC)},
            )

            # Store essay
            self.essays[essay_id] = essay

            # Register constraint
            if constraint_key:
                self._unique_constraints[constraint_key] = essay_id

            self.logger.info(f"Created essay {essay_id} with content idempotency check")
            return (True, essay_id)

    def get_session_factory(self) -> Any:
        """
        Get the session factory for transaction management.

        Returns None for mock implementation.
        """
        return self._session_factory

    async def update_essay_processing_metadata(
        self,
        essay_id: str,
        metadata_updates: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Update essay processing metadata fields."""
        _ = session  # Explicitly ignore for protocol compliance

        async with self._get_lock(essay_id):
            essay = self.essays.get(essay_id)
            if not essay:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_processing_metadata",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            essay.processing_metadata.update(metadata_updates)
            essay.updated_at = datetime.now(UTC)

            self.logger.info(f"Updated processing metadata for essay {essay_id}")

    async def update_student_association(
        self,
        essay_id: str,
        student_id: str | None,
        association_confirmed_at: Any,  # datetime
        association_method: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Update essay with student association from Phase 1 matching."""
        _ = session  # Explicitly ignore for protocol compliance

        async with self._get_lock(essay_id):
            essay = self.essays.get(essay_id)
            if not essay:
                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_student_association",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=correlation_id,
                )

            if student_id is not None:
                essay.update_student_association(
                    student_id=student_id,
                    association_method=association_method,
                    confirmed_at=association_confirmed_at,
                )
            else:
                # Handle case where student_id is None (clearing association)
                essay.student_id = None
                essay.association_method = association_method
                essay.association_confirmed_at = association_confirmed_at
                essay.updated_at = datetime.now(UTC)

            self.logger.info(f"Updated student association for essay {essay_id}")
