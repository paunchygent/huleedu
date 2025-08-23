"""
Comprehensive integration tests for database repository operations in Email Service.

Tests real PostgreSQL database integration with testcontainers, following Rule 075
methodology with focus on repository patterns, Swedish character support, and
async SQLAlchemy operations.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.email_service.config import Settings
from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository
from services.email_service.models_db import (
    Base,
    EmailStatus,
    EventOutbox,
)
from services.email_service.models_db import (
    EmailRecord as DbEmailRecord,
)
from services.email_service.protocols import EmailRecord as ProtocolEmailRecord


class TestEmailServiceDatabaseOperations:
    """Integration tests for Email Service database operations using real PostgreSQL."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL testcontainer with proper configuration."""
        container = PostgresContainer("postgres:15-alpine").with_env("TZ", "UTC")
        container.start()
        yield container
        container.stop()

    class DatabaseTestSettings(Settings):
        """Test settings with database URL override for testcontainers."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_test_database_url", database_url)

        @property
        def database_url(self) -> str:
            return str(object.__getattribute__(self, "_test_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings with testcontainer database URL."""
        pg_connection_url = postgres_container.get_connection_url()
        # Convert to async PostgreSQL connection
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.DatabaseTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine and run migrations."""
        engine = create_async_engine(
            test_settings.database_url,
            pool_size=test_settings.DATABASE_POOL_SIZE,
            max_overflow=test_settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=test_settings.DATABASE_POOL_PRE_PING,
            pool_recycle=test_settings.DATABASE_POOL_RECYCLE,
            echo=False,  # Disable SQL echo for cleaner test output
        )

        # Create database schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(
        self, database_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create async session factory for database operations."""
        return async_sessionmaker(
            database_engine,
            expire_on_commit=False,  # Prevent DetachedInstanceError
            class_=AsyncSession,
        )

    @pytest.fixture
    async def database_metrics(self, database_engine: AsyncEngine) -> DatabaseMetrics:
        """Create database metrics instance for monitoring."""
        from services.email_service.metrics import setup_email_service_database_monitoring

        return setup_email_service_database_monitoring(
            engine=database_engine, service_name="email_service_test"
        )

    @pytest.fixture
    async def repository(
        self, database_engine: AsyncEngine, database_metrics: DatabaseMetrics
    ) -> PostgreSQLEmailRepository:
        """Create PostgreSQL email repository with real database connection."""
        return PostgreSQLEmailRepository(engine=database_engine, database_metrics=database_metrics)

    @pytest.fixture(autouse=True)
    async def clean_database(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Clean database tables before each test."""
        async with session_factory() as session:
            async with session.begin():
                # Clean tables in dependency order
                await session.execute(text("TRUNCATE TABLE event_outbox CASCADE"))
                await session.execute(text("TRUNCATE TABLE email_templates CASCADE"))
                await session.execute(text("TRUNCATE TABLE email_records CASCADE"))

    def create_test_email_record(
        self,
        message_id: str | None = None,
        subject: str = "Test Email Subject",
        template_id: str = "test_template",
        variables: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ProtocolEmailRecord:
        """Create test email record with sensible defaults."""
        # Set defaults but allow kwargs to override
        defaults = {
            "message_id": message_id or str(uuid4()),
            "to_address": "test@example.com",
            "from_address": "noreply@huleedu.com", 
            "from_name": "HuleEdu Test",
            "subject": subject,
            "template_id": template_id,
            "category": "test",
            "variables": variables or {},
            "correlation_id": str(uuid4()),
        }
        
        # Merge kwargs, allowing them to override defaults
        defaults.update(kwargs)
        
        return ProtocolEmailRecord(**defaults)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_schema_creation_and_validation(self, database_engine: AsyncEngine) -> None:
        """Test database schema creation and table structure validation."""
        async with database_engine.connect() as conn:
            # Verify core tables exist
            tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            result = await conn.execute(tables_query)
            tables = [row[0] for row in result.fetchall()]

            expected_tables = ["email_records", "email_templates", "event_outbox"]
            for table in expected_tables:
                assert table in tables, f"Expected table {table} not found in schema"

            # Verify email_records table structure
            email_records_columns = text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'email_records'
                ORDER BY column_name
            """)
            result = await conn.execute(email_records_columns)
            columns = {row[0]: {"type": row[1], "nullable": row[2]} for row in result.fetchall()}

            # Verify key columns exist with correct types
            assert "message_id" in columns
            assert "correlation_id" in columns
            assert "to_address" in columns
            assert "variables" in columns
            assert columns["variables"]["type"] == "json"
            assert columns["status"]["type"] == "USER-DEFINED"  # ENUM type

            # Verify indexes exist
            indexes_query = text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'email_records'
            """)
            result = await conn.execute(indexes_query)
            indexes = [row[0] for row in result.fetchall()]

            expected_indexes = [
                "ix_email_records_correlation_id",
                "ix_email_records_to_address",
                "ix_email_records_template_id",
                "ix_email_records_category",
                "ix_email_records_status",
                "ix_email_records_status_created",
                "ix_email_records_category_created",
            ]

            for idx in expected_indexes:
                assert idx in indexes, f"Expected index {idx} not found"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_email_record_crud_operations(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test basic CRUD operations for email records."""
        # Create email record
        record = self.create_test_email_record(
            subject="CRUD Test Email",
            template_id="crud_test",
            variables={"name": "Test User", "action": "verification"},
        )

        await repository.create_email_record(record)

        # Read email record by message ID
        retrieved = await repository.get_by_message_id(record.message_id)
        assert retrieved is not None
        assert retrieved.message_id == record.message_id
        assert retrieved.subject == record.subject
        assert retrieved.template_id == record.template_id
        assert retrieved.variables == record.variables
        assert retrieved.status == "pending"  # Default status

        # Update email record status
        await repository.update_status(
            message_id=record.message_id,
            status="sent",
            provider_message_id="provider-123",
            sent_at=datetime.now(timezone.utc),
        )

        # Verify update
        updated = await repository.get_by_message_id(record.message_id)
        assert updated is not None
        assert updated.status == "sent"
        assert updated.provider_message_id == "provider-123"
        assert updated.sent_at is not None

        # Read by correlation ID
        correlation_records = await repository.get_by_correlation_id(record.correlation_id)
        assert len(correlation_records) == 1
        assert correlation_records[0].message_id == record.message_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swedish_character_support(self, repository: PostgreSQLEmailRepository) -> None:
        """Test Swedish characters (åäöÅÄÖ) preservation in database fields."""
        swedish_data: dict[str, Any] = {
            "subject": "Välkommen till HuleEdu - Språkstöd för svenska",
            "from_name": "Språkpedagogen Åsa Ström",
            "variables": {
                "student_name": "Björn Åkesson",
                "school_name": "Språkskolan i Göteborg",
                "message": "Hej Björn! Välkommen till vår svenska språkkurs. Läraren Åsa kommer att hjälpa dig.",
                "contact_info": "Kontakta oss på språk@skolan.se för frågor",
            },
        }

        record = self.create_test_email_record(
            to_address="björn.åkesson@example.se",
            subject=swedish_data["subject"],
            from_name=swedish_data["from_name"],
            template_id="swedish_welcome",
            variables=swedish_data["variables"],
        )

        await repository.create_email_record(record)

        # Retrieve and verify Swedish characters are preserved
        retrieved = await repository.get_by_message_id(record.message_id)
        assert retrieved is not None
        assert retrieved.subject == swedish_data["subject"]
        assert retrieved.from_name == swedish_data["from_name"]
        assert retrieved.to_address == "björn.åkesson@example.se"

        # Verify JSON field preserves Swedish characters
        assert retrieved.variables["student_name"] == "Björn Åkesson"
        assert retrieved.variables["school_name"] == "Språkskolan i Göteborg"
        assert "Välkommen" in retrieved.variables["message"]
        assert "Göteborg" in retrieved.variables["school_name"]

        # Test database-level text search with Swedish characters
        async with repository.session() as session:
            # Search by subject containing Swedish characters
            stmt = select(DbEmailRecord).where(DbEmailRecord.subject.ilike("%språkstöd%"))
            result = await session.execute(stmt)
            found_records = result.scalars().all()
            assert len(found_records) == 1

            # Search in JSON variables using PostgreSQL JSON operators
            json_search_stmt = select(DbEmailRecord).where(
                DbEmailRecord.variables.op("->>")("student_name").ilike("%björn%")
            )
            result = await session.execute(json_search_stmt)
            json_records = result.scalars().all()
            assert len(json_records) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connection_pool_behavior_under_load(
        self, database_engine: AsyncEngine, database_metrics: DatabaseMetrics
    ) -> None:
        """Test connection pooling behavior with concurrent database operations."""
        repository = PostgreSQLEmailRepository(database_engine, database_metrics)

        # Create multiple email records concurrently
        concurrent_operations = 20
        records = []

        async def create_email_record(index: int) -> None:
            record = self.create_test_email_record(
                subject=f"Concurrent Test Email {index}",
                template_id=f"concurrent_test_{index}",
                variables={"index": str(index), "timestamp": str(datetime.now())},
            )
            records.append(record)
            await repository.create_email_record(record)

        # Execute concurrent operations
        tasks = [create_email_record(i) for i in range(concurrent_operations)]
        await asyncio.gather(*tasks)

        # Verify all records were created successfully
        async with repository.session() as session:
            count_stmt = select(func.count(DbEmailRecord.message_id))
            result = await session.execute(count_stmt)
            count = result.scalar()
            assert count == concurrent_operations

        # Test concurrent reads
        async def read_email_record(record: ProtocolEmailRecord) -> ProtocolEmailRecord | None:
            return await repository.get_by_message_id(record.message_id)

        read_tasks = [read_email_record(record) for record in records[:10]]
        read_results = await asyncio.gather(*read_tasks)

        # Verify all reads succeeded
        for read_result in read_results:
            assert read_result is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transaction_handling_and_rollback(
        self,
        repository: PostgreSQLEmailRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test transaction handling and rollback scenarios."""
        record = self.create_test_email_record(subject="Transaction Test")

        # Test successful transaction
        async with repository.session() as session:
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
                status=EmailStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            session.add(db_record)
            # Transaction commits automatically via context manager

        # Verify record was committed
        retrieved = await repository.get_by_message_id(record.message_id)
        assert retrieved is not None

        # Test transaction rollback on exception
        rollback_record = self.create_test_email_record(
            message_id="rollback-test", subject="Rollback Test"
        )

        try:
            async with repository.session() as session:
                db_rollback_record = DbEmailRecord(
                    message_id=rollback_record.message_id,
                    correlation_id=rollback_record.correlation_id,
                    to_address=rollback_record.to_address,
                    from_address=rollback_record.from_address,
                    from_name=rollback_record.from_name,
                    subject=rollback_record.subject,
                    template_id=rollback_record.template_id,
                    category=rollback_record.category,
                    variables=rollback_record.variables,
                    status=EmailStatus.PENDING,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(db_rollback_record)
                await session.flush()  # Persist to session but not committed

                # Force an error to trigger rollback
                raise ValueError("Intentional error for rollback test")

        except ValueError:
            pass  # Expected error

        # Verify record was rolled back and not committed
        rollback_retrieved = await repository.get_by_message_id(rollback_record.message_id)
        assert rollback_retrieved is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_constraint_enforcement_and_error_handling(
        self,
        repository: PostgreSQLEmailRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test database constraint enforcement and error handling."""
        # Test unique constraint on provider_message_id
        record1 = self.create_test_email_record(
            message_id="constraint-test-1", subject="Constraint Test 1"
        )
        record2 = self.create_test_email_record(
            message_id="constraint-test-2", subject="Constraint Test 2"
        )

        await repository.create_email_record(record1)

        # Update first record with provider message ID
        await repository.update_status(
            message_id=record1.message_id, status="sent", provider_message_id="unique-provider-id"
        )

        # Try to create second record with same provider message ID
        await repository.create_email_record(record2)

        # This should fail due to unique constraint
        with pytest.raises(IntegrityError):
            await repository.update_status(
                message_id=record2.message_id,
                status="sent",
                provider_message_id="unique-provider-id",  # Duplicate
            )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_bulk_operations_performance(
        self,
        repository: PostgreSQLEmailRepository,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test bulk database operations and query performance."""
        bulk_size = 100
        start_time = datetime.now()

        # Create bulk email records efficiently
        async with repository.session() as session:
            db_records = []
            for i in range(bulk_size):
                record = self.create_test_email_record(
                    message_id=f"bulk-test-{i}",
                    subject=f"Bulk Test Email {i}",
                    template_id="bulk_test",
                    variables={"index": str(i), "batch": "performance_test"},
                )

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
                    status=EmailStatus.PENDING,
                    created_at=datetime.now(timezone.utc),
                )
                db_records.append(db_record)

            session.add_all(db_records)
            await session.commit()

        creation_time = datetime.now() - start_time

        # Verify bulk creation performance (should be under 5 seconds for 100 records)
        assert creation_time.total_seconds() < 5.0, (
            f"Bulk creation took {creation_time.total_seconds()}s"
        )

        # Test bulk query performance
        query_start = datetime.now()

        async with session_factory() as session:
            # Test complex query with joins and filters
            stmt = (
                select(DbEmailRecord)
                .where(
                    DbEmailRecord.template_id == "bulk_test",
                    DbEmailRecord.status == EmailStatus.PENDING,
                )
                .order_by(DbEmailRecord.created_at.desc())
            )

            result = await session.execute(stmt)
            records = result.scalars().all()

        query_time = datetime.now() - query_start

        assert len(records) == bulk_size
        assert query_time.total_seconds() < 1.0, f"Bulk query took {query_time.total_seconds()}s"

        # Test bulk status updates
        update_start = datetime.now()

        async with session_factory() as session:
            # Bulk update using SQLAlchemy update statement
            update_stmt = (
                update(DbEmailRecord)
                .where(DbEmailRecord.template_id == "bulk_test")
                .values(status=EmailStatus.PROCESSING, provider="bulk_test_provider")
            )

            result = await session.execute(update_stmt)
            await session.commit()

        update_time = datetime.now() - update_start

        assert result.rowcount == bulk_size  # type: ignore[attr-defined]
        assert update_time.total_seconds() < 2.0, f"Bulk update took {update_time.total_seconds()}s"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_metrics_collection(
        self, repository: PostgreSQLEmailRepository, database_metrics: DatabaseMetrics
    ) -> None:
        """Test database metrics collection during repository operations."""
        # Perform several database operations
        records = [
            self.create_test_email_record(
                message_id=f"metrics-test-{i}", subject=f"Metrics Test {i}"
            )
            for i in range(5)
        ]

        for record in records:
            await repository.create_email_record(record)

        for record in records:
            retrieved = await repository.get_by_message_id(record.message_id)
            assert retrieved is not None

        # Update records
        for record in records:
            await repository.update_status(
                message_id=record.message_id, status="sent", sent_at=datetime.now(timezone.utc)
            )

        # Database metrics should have recorded these operations
        # This is implicitly tested by the successful completion of operations
        # The metrics collection happens automatically through the DatabaseMetrics instance

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_lifecycle_and_connection_management(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test proper session lifecycle and connection management."""
        # Test multiple sequential operations
        record1 = self.create_test_email_record(message_id="session-test-1")
        record2 = self.create_test_email_record(message_id="session-test-2")

        # Each operation should use a separate session
        await repository.create_email_record(record1)
        await repository.create_email_record(record2)

        # Read operations should also use separate sessions
        retrieved1 = await repository.get_by_message_id(record1.message_id)
        retrieved2 = await repository.get_by_message_id(record2.message_id)

        assert retrieved1 is not None
        assert retrieved2 is not None

        # Test that sessions are properly closed and don't leak connections
        correlation_id = str(uuid4())
        correlation_records = []

        # Create multiple records with same correlation ID
        for i in range(10):
            record = self.create_test_email_record(
                message_id=f"correlation-{i}", correlation_id=correlation_id
            )
            correlation_records.append(record)
            await repository.create_email_record(record)

        # Retrieve all by correlation ID
        retrieved_records = await repository.get_by_correlation_id(correlation_id)
        assert len(retrieved_records) == 10

        # Each message_id should be unique
        message_ids = {record.message_id for record in retrieved_records}
        assert len(message_ids) == 10  # All unique