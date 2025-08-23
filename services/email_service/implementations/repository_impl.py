"""PostgreSQL repository implementation for Email Service.

This module provides the concrete implementation of EmailRepository protocol,
following the established pattern from CJ Assessment Service with proper
session management and error handling.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.email_service.models_db import EmailRecord as DbEmailRecord
from services.email_service.models_db import EmailStatus
from services.email_service.protocols import EmailRecord, EmailRepository

logger = create_service_logger("email_service.repository.postgres")


class PostgreSQLEmailRepository(EmailRepository):
    """PostgreSQL implementation of EmailRepository for Email Service.

    Follows the established pattern from CJ Assessment Service with:
    - Engine injection from DI container
    - Repository-managed session maker
    - Context manager for session lifecycle
    - Proper error handling and logging
    """

    def __init__(
        self, engine: AsyncEngine, database_metrics: Optional[DatabaseMetrics] = None
    ) -> None:
        """Initialize the repository with injected database engine.

        Args:
            engine: AsyncEngine injected from DI container
            database_metrics: Optional database metrics for monitoring
        """
        self.engine = engine
        self.database_metrics = database_metrics
        self.logger = create_service_logger("email_service.repository.postgres")

        # Create session maker following CJ Assessment pattern
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,  # Prevent DetachedInstanceError
            class_=AsyncSession,
        )

        self.logger.info("PostgreSQL Email Repository initialized")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Context manager for database sessions.

        Provides automatic transaction management with commit/rollback.
        """
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_email_record(self, record: EmailRecord) -> None:
        """Create a new email record in the database.

        Args:
            record: EmailRecord to persist
        """
        self.logger.debug(f"Creating email record: {record.message_id}")

        async with self.session() as session:
            # Convert protocol model to database model
            db_record = DbEmailRecord(
                message_id=record.message_id,
                correlation_id=record.correlation_id,
                to_address=record.to_address,
                from_address=record.from_address,
                from_name=record.from_name,
                subject=record.subject,
                template_id=record.template_id,
                category=record.category,
                variables=record.variables,
                provider=record.provider,
                provider_message_id=record.provider_message_id,
                status=EmailStatus(record.status),  # Convert string to enum
                failure_reason=record.failure_reason,
                created_at=record.created_at or datetime.now(timezone.utc),
                sent_at=record.sent_at,
                failed_at=record.failed_at,
            )

            session.add(db_record)
            await session.flush()  # Ensure record is persisted

            self.logger.info(f"Created email record: {record.message_id}")

    async def update_status(
        self,
        message_id: str,
        status: str,
        provider_message_id: str | None = None,
        provider_response: str | None = None,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Update email record status and metadata.

        Args:
            message_id: Email message ID to update
            status: New status (sent, failed, etc.)
            provider_message_id: Provider's message ID
            provider_response: Provider's response details (not used in current schema)
            sent_at: Timestamp when email was sent
            failed_at: Timestamp when email failed
            failure_reason: Reason for failure
        """
        self.logger.debug(f"Updating email record status: {message_id} -> {status}")

        async with self.session() as session:
            # Get the existing record
            stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
            result = await session.execute(stmt)
            db_record = result.scalar_one_or_none()

            if not db_record:
                self.logger.error(f"Email record not found for update: {message_id}")
                return

            # Update fields
            db_record.status = EmailStatus(status)

            if provider_message_id is not None:
                db_record.provider_message_id = provider_message_id

            if sent_at is not None:
                db_record.sent_at = sent_at

            if failed_at is not None:
                db_record.failed_at = failed_at

            if failure_reason is not None:
                db_record.failure_reason = failure_reason

            await session.flush()

            self.logger.info(f"Updated email record status: {message_id} -> {status}")

    async def get_by_message_id(self, message_id: str) -> EmailRecord | None:
        """Get email record by message ID.

        Args:
            message_id: Email message ID to retrieve

        Returns:
            EmailRecord if found, None otherwise
        """
        self.logger.debug(f"Getting email record by message_id: {message_id}")

        async with self.session() as session:
            stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
            result = await session.execute(stmt)
            db_record = result.scalar_one_or_none()

            if not db_record:
                self.logger.debug(f"No email record found for message_id: {message_id}")
                return None

            # Convert database model to protocol model
            return self._db_record_to_protocol(db_record)

    async def get_by_correlation_id(self, correlation_id: str) -> list[EmailRecord]:
        """Get email records by correlation ID.

        Args:
            correlation_id: Correlation ID for request tracking

        Returns:
            List of EmailRecord objects
        """
        self.logger.debug(f"Getting email records by correlation_id: {correlation_id}")

        async with self.session() as session:
            stmt = select(DbEmailRecord).where(DbEmailRecord.correlation_id == correlation_id)
            result = await session.execute(stmt)
            db_records = result.scalars().all()

            # Convert database models to protocol models
            records = [self._db_record_to_protocol(db_record) for db_record in db_records]

            self.logger.debug(
                f"Found {len(records)} email records for correlation_id: {correlation_id}"
            )
            return records

    def _db_record_to_protocol(self, db_record: DbEmailRecord) -> EmailRecord:
        """Convert database model to protocol model.

        Args:
            db_record: Database email record

        Returns:
            EmailRecord protocol model
        """
        return EmailRecord(
            message_id=db_record.message_id,
            to_address=db_record.to_address,
            from_address=db_record.from_address,
            from_name=db_record.from_name,
            subject=db_record.subject,
            template_id=db_record.template_id,
            category=db_record.category,
            variables=db_record.variables,
            correlation_id=db_record.correlation_id,
            html_content=None,  # Not stored in database
            text_content=None,  # Not stored in database
            provider=db_record.provider,
            provider_message_id=db_record.provider_message_id,
            status=db_record.status.value,  # Convert enum to string
            created_at=db_record.created_at,
            sent_at=db_record.sent_at,
            failed_at=db_record.failed_at,
            failure_reason=db_record.failure_reason,
        )
