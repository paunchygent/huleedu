"""
Facade PostgreSQL repository implementation for Essay Lifecycle Service.

Thin orchestrator that delegates to specialized modules following SRP and DDD principles.
Uses injected session_factory instead of creating its own engine.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.essay_lifecycle_service.domain_models import EssayState as ConcreteEssayState
from services.essay_lifecycle_service.implementations.essay_repository_idempotency import (
    EssayIdempotencyOperations,
)
from services.essay_lifecycle_service.implementations.essay_repository_queries import (
    EssayRepositoryQueries,
)
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState


class PostgreSQLEssayRepository(EssayRepositoryProtocol):
    """Facade for PostgreSQL essay repository operations."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        database_metrics: DatabaseMetrics | None = None,
    ) -> None:
        """Initialize the repository facade with injected session factory."""
        self.session_factory = session_factory
        self.database_metrics = database_metrics
        self.logger = create_service_logger("els.repository.postgres")

        # Delegate to specialized modules
        self.queries = EssayRepositoryQueries()
        self.idempotency = EssayIdempotencyOperations()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database sessions with proper transaction handling."""
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def get_session_factory(self) -> async_sessionmaker:
        """Get the session factory for transaction management."""
        return self.session_factory

    async def get_essay_state(
        self, essay_id: str, session: AsyncSession | None = None
    ) -> ConcreteEssayState | None:
        """Retrieve essay state by ID."""
        if session is None:
            async with self.session() as session:
                return await self.queries.get_essay_state(session, essay_id)
        return await self.queries.get_essay_state(session, essay_id)

    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state with new status, metadata, and optional storage reference."""
        if session is None:
            async with self.session() as session:
                return await self.queries.update_essay_state(
                    session, essay_id, new_status, metadata, storage_reference, correlation_id
                )
        return await self.queries.update_essay_state(
            session, essay_id, new_status, metadata, storage_reference, correlation_id
        )

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
        await self.update_essay_state(
            essay_id,
            new_status,
            metadata,
            session,
            storage_reference=storage_reference,
            correlation_id=correlation_id,
        )

    async def create_essay_record(
        self,
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> ConcreteEssayState:
        """Create new essay record from primitive parameters."""
        if session is None:
            async with self.session() as session:
                return await self.queries.create_essay_record(
                    session, essay_id, batch_id, entity_type, correlation_id
                )
        return await self.queries.create_essay_record(
            session, essay_id, batch_id, entity_type, correlation_id
        )

    async def create_essay_records_batch(
        self,
        essay_data: list[dict[str, str | None]],
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> list[EssayState]:
        """Create multiple essay records in single atomic transaction."""
        if session is None:
            async with self.session() as session:
                return await self.queries.create_essay_records_batch(
                    session, essay_data, correlation_id
                )
        return await self.queries.create_essay_records_batch(session, essay_data, correlation_id)

    async def update_essay_processing_metadata(
        self,
        essay_id: str,
        metadata_updates: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Update essay processing metadata fields."""
        if session is None:
            async with self.session() as session:
                return await self.queries.update_essay_processing_metadata(
                    session, essay_id, metadata_updates, correlation_id
                )
        return await self.queries.update_essay_processing_metadata(
            session, essay_id, metadata_updates, correlation_id
        )

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
        if session is None:
            async with self.session() as session:
                return await self.queries.update_student_association(
                    session,
                    essay_id,
                    student_id,
                    association_confirmed_at,
                    association_method,
                    correlation_id,
                )
        return await self.queries.update_student_association(
            session,
            essay_id,
            student_id,
            association_confirmed_at,
            association_method,
            correlation_id,
        )

    async def list_essays_by_batch(self, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        async with self.session() as session:
            return await self.queries.list_essays_by_batch(session, batch_id)

    async def get_batch_status_summary(
        self, batch_id: str, session: AsyncSession | None = None
    ) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch using efficient SQL aggregation."""
        if session is None:
            async with self.session() as session:
                return await self.queries.get_batch_status_summary(session, batch_id)
        return await self.queries.get_batch_status_summary(session, batch_id)

    async def get_batch_summary_with_essays(
        self, batch_id: str
    ) -> tuple[list[EssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation."""
        async with self.session() as session:
            return await self.queries.get_batch_summary_with_essays(session, batch_id)

    async def get_essay_by_text_storage_id_and_batch_id(
        self, batch_id: str, text_storage_id: str
    ) -> ConcreteEssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        async with self.session() as session:
            return await self.queries.get_essay_by_text_storage_id_and_batch_id(
                session, batch_id, text_storage_id
            )

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
    ) -> ConcreteEssayState:
        """Create or update essay state for slot assignment with content metadata."""
        if session is None:
            async with self.session() as session:
                return await self.idempotency.create_or_update_essay_state_for_slot_assignment(
                    session,
                    internal_essay_id,
                    batch_id,
                    text_storage_id,
                    original_file_name,
                    file_size,
                    content_hash,
                    initial_status,
                    correlation_id,
                )
        return await self.idempotency.create_or_update_essay_state_for_slot_assignment(
            session,
            internal_essay_id,
            batch_id,
            text_storage_id,
            original_file_name,
            file_size,
            content_hash,
            initial_status,
            correlation_id,
        )

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str, session: AsyncSession | None = None
    ) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        if session is None:
            async with self.session() as session:
                return await self.queries.list_essays_by_batch_and_phase(
                    session, batch_id, phase_name
                )
        return await self.queries.list_essays_by_batch_and_phase(session, batch_id, phase_name)

    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> tuple[bool, str | None]:
        """Create essay state with atomic idempotency check for content provisioning."""
        if session is None:
            async with self.session() as session:
                return await self.idempotency.create_essay_state_with_content_idempotency(
                    session, batch_id, text_storage_id, essay_data, correlation_id
                )
        return await self.idempotency.create_essay_state_with_content_idempotency(
            session, batch_id, text_storage_id, essay_data, correlation_id
        )
