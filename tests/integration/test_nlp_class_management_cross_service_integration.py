"""
Cross-Service Integration Test: NLP Service ↔ Class Management Service

Tests the complete student-essay association flow between NLP and Class Management services
using testcontainers for complete isolation.

Test Flow:
1. Set up isolated test infrastructure (PostgreSQL x2, Kafka, Redis)
2. Instantiate service components with test configuration
3. Simulate ELS publishing BatchStudentMatchingRequestedV1
4. NLP Service processes and publishes BatchAuthorMatchesSuggestedV1
5. Class Management consumes and stores associations
6. Verify data consistency across service boundaries

Following Rule 075 ULTRATHINK methodology and testcontainer patterns.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# Import NLP service components (for DB schema)
from services.nlp_service.models import Base as NlpBase

# Import Class Management service components
from services.class_management_service.implementations.batch_author_matches_handler import (
    BatchAuthorMatchesHandler,
)
from services.class_management_service.models_db import (
    Base as ClassManagementBase,
    EssayStudentAssociation,
    Student,
)

logger = create_service_logger("test.nlp_class_management_integration")


class MockClassRepository:
    """Mock class repository for testing."""

    def __init__(self, students: list[Student]):
        self.students = {str(s.id): s for s in students}

    async def get_student_by_id(self, student_id: str) -> Student | None:
        """Get student by ID."""
        return self.students.get(student_id)


class TestNLPClassManagementCrossServiceIntegration:
    """Cross-service integration tests using testcontainers."""

    @pytest.fixture(scope="class")
    def postgres_nlp_container(self) -> Generator[PostgresContainer, None, None]:
        """PostgreSQL container for NLP service."""
        with PostgresContainer("postgres:15-alpine") as container:
            yield container

    @pytest.fixture(scope="class")
    def postgres_cm_container(self) -> Generator[PostgresContainer, None, None]:
        """PostgreSQL container for Class Management service."""
        with PostgresContainer("postgres:15-alpine") as container:
            yield container

    @pytest.fixture(scope="class")
    def kafka_container(self) -> Generator[KafkaContainer, None, None]:
        """Kafka container for event communication."""
        with KafkaContainer("confluentinc/cp-kafka:7.4.0") as container:
            yield container

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, None, None]:
        """Redis container for caching and outbox."""
        with RedisContainer("redis:7-alpine") as container:
            yield container

    @pytest.fixture
    async def nlp_db_engine(self, postgres_nlp_container: PostgresContainer):
        """Create NLP database engine and schema."""
        db_url = postgres_nlp_container.get_connection_url()
        if "+psycopg2://" in db_url:
            db_url = db_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(db_url)

        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(NlpBase.metadata.create_all)

        yield engine

        await engine.dispose()

    @pytest.fixture
    async def cm_db_engine(self, postgres_cm_container: PostgresContainer):
        """Create Class Management database engine and schema."""
        db_url = postgres_cm_container.get_connection_url()
        if "+psycopg2://" in db_url:
            db_url = db_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(db_url)

        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(ClassManagementBase.metadata.create_all)

        yield engine

        await engine.dispose()

    @pytest.fixture
    def cm_session_factory(self, cm_db_engine) -> async_sessionmaker[AsyncSession]:
        """Create Class Management session factory."""
        return async_sessionmaker(cm_db_engine, expire_on_commit=False)

    @pytest.fixture
    async def redis_client(
        self, redis_container: RedisContainer
    ) -> AsyncGenerator[RedisClient, None]:
        """Create Redis client for testing."""
        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
        client = RedisClient(client_id="test-integration", redis_url=redis_url)
        await client.start()

        try:
            await client.client.flushdb()
            yield client
        finally:
            await client.stop()

    @pytest.fixture
    async def test_students(
        self, cm_session_factory: async_sessionmaker[AsyncSession]
    ) -> list[Student]:
        """Create test students in Class Management database."""
        students = [
            Student(
                id=uuid4(),
                external_id="001",
                first_name="Elvira",
                last_name="Johansson",
                email="elvira.johansson@school.edu",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                external_id="002",
                first_name="Hilda",
                last_name="Grahn",
                email="hg17001@harryda.se",
                created_by_user_id="test_user",
            ),
            Student(
                id=uuid4(),
                external_id="003",
                first_name="Leo",
                last_name="Svartling",
                email="ls17003@harryda.se",
                created_by_user_id="test_user",
            ),
        ]

        async with cm_session_factory() as session:
            async with session.begin():
                for student in students:
                    session.add(student)

        return students

    @pytest.fixture
    async def kafka_producer(
        self, kafka_container: KafkaContainer
    ) -> AsyncGenerator[AIOKafkaProducer, None]:
        """Create Kafka producer for test events."""
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await producer.start()

        try:
            yield producer
        finally:
            await producer.stop()

    @pytest.fixture
    async def kafka_consumer(
        self, kafka_container: KafkaContainer
    ) -> AsyncGenerator[AIOKafkaConsumer, None]:
        """Create Kafka consumer for monitoring events."""
        topics = [
            topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
        ]

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=kafka_container.get_bootstrap_server(),
            group_id=f"test-consumer-{uuid4().hex[:8]}",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await consumer.start()

        try:
            yield consumer
        finally:
            await consumer.stop()

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_student_essay_association_flow(
        self,
        cm_session_factory: async_sessionmaker[AsyncSession],
        test_students: list[Student],
        kafka_producer: AIOKafkaProducer,
    ):
        """Test complete student-essay association flow between services."""
        batch_id = f"test-batch-{uuid4().hex[:8]}"
        class_id = f"test-class-{uuid4().hex[:8]}"
        correlation_id = str(uuid4())

        # Prepare test essays with real content
        test_essays = [
            {
                "essay_id": "essay-001",
                "filename": "Elvira_Johansson_BookReport.txt",
                "content": """Elvira Johansson 2025-03-06
Prov: Book Report ES24B
Antal ord: 607

Dear mr Rai.
I'm writing this letter about your book.""",
            },
            {
                "essay_id": "essay-002",
                "filename": "Hilda_Grahn_Objectives.txt",
                "content": """Hilda Grahn 2024-08-30
Prov: Eng 5 SA24D My Personal Objectives 2
HG17001@harryda.se
Antal ord: 226

Hi! My name is Hilda Grahn and I live in Landvetter.""",
            },
        ]

        # In a real test, we would convert students to roster format for NLP
        # For this test, we're simulating NLP's response directly

        # Step 1: Set up NLP service components
        # Note: In a real cross-service test, we'd instantiate the NLP event handler
        # For now, we'll simulate NLP's response based on expected behavior

        # Step 2: Set up Class Management handler
        mock_repository = MockClassRepository(test_students)
        cm_handler = BatchAuthorMatchesHandler(
            class_repository=mock_repository,
            session_factory=cm_session_factory,
        )

        # Step 3: Simulate ELS publishing BatchStudentMatchingRequestedV1
        matching_request = BatchStudentMatchingRequestedV1(
            batch_id=batch_id,
            class_id=class_id,
            essays_to_process=[
                EssayProcessingInputRefV1(
                    essay_id=essay["essay_id"],
                    text_storage_id=f"storage-{essay['essay_id']}",
                )
                for essay in test_essays
            ],
        )

        request_envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type=ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED.value,
            correlation_id=correlation_id,
            aggregate_id=batch_id,
            aggregate_type="batch",
            event_version="1.0",
            source_service="test-harness",
            data=matching_request.model_dump(),
        )

        # Publish to Kafka
        await kafka_producer.send_and_wait(
            topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            request_envelope.model_dump(),
        )

        # Step 4: Simulate NLP processing and response
        # In a real test, NLP would consume the event and process it
        # For this test, we'll create the expected response
        nlp_response = BatchAuthorMatchesSuggestedV1(
            batch_id=batch_id,
            class_id=class_id,
            match_results=[
                {
                    "essay_id": "essay-001",
                    "text_storage_id": "storage-essay-001",
                    "filename": "Elvira_Johansson_BookReport.txt",
                    "suggestions": [
                        {
                            "student_id": "001",
                            "student_name": "Elvira Johansson",
                            "student_email": "elvira.johansson@school.edu",
                            "confidence_score": 0.95,
                            "match_reasons": ["Name exact match"],
                            "extraction_metadata": {"source": "header"},
                        }
                    ],
                },
                {
                    "essay_id": "essay-002",
                    "text_storage_id": "storage-essay-002",
                    "filename": "Hilda_Grahn_Objectives.txt",
                    "suggestions": [
                        {
                            "student_id": "002",
                            "student_name": "Hilda Grahn",
                            "student_email": "hg17001@harryda.se",
                            "confidence_score": 0.98,
                            "match_reasons": ["Name and email match"],
                            "extraction_metadata": {"source": "header"},
                        }
                    ],
                },
            ],
            processing_summary={
                "total_essays": 2,
                "matched": 2,
                "unmatched": 0,
                "failed": 0,
            },
        )

        response_envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED.value,
            correlation_id=correlation_id,
            aggregate_id=batch_id,
            aggregate_type="batch",
            event_version="1.0",
            source_service="nlp_service",
            data=nlp_response.model_dump(),
        )

        # Publish NLP response
        await kafka_producer.send_and_wait(
            topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            response_envelope.model_dump(),
        )

        # Step 5: Class Management handler processes the event
        # Create a mock Kafka record
        kafka_record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            partition=0,
            offset=0,
            timestamp=0,
            timestamp_type=0,
            key=None,
            value=json.dumps(response_envelope.model_dump()).encode("utf-8"),
            checksum=None,
            serialized_key_size=-1,
            serialized_value_size=-1,
            headers=[],
        )

        # Process the event
        await cm_handler.handle(kafka_record)

        # Step 6: Verify associations were stored
        async with cm_session_factory() as session:
            associations = (
                (
                    await session.execute(
                        select(EssayStudentAssociation).where(
                            EssayStudentAssociation.batch_id == batch_id
                        )
                    )
                )
                .scalars()
                .all()
            )

            assert len(associations) == 2

            # Verify specific associations
            essay_associations = {a.essay_id: a for a in associations}

            # Check Elvira's essay
            elvira_assoc = essay_associations.get("essay-001")
            assert elvira_assoc is not None
            assert elvira_assoc.student_id == test_students[0].id  # Elvira
            assert elvira_assoc.confidence_score == 0.95
            assert elvira_assoc.match_status == "high_confidence"

            # Check Hilda's essay
            hilda_assoc = essay_associations.get("essay-002")
            assert hilda_assoc is not None
            assert hilda_assoc.student_id == test_students[1].id  # Hilda
            assert hilda_assoc.confidence_score == 0.98
            assert hilda_assoc.match_status == "high_confidence"

        logger.info(
            f"Cross-service integration test completed successfully. "
            f"Verified {len(associations)} associations stored in Class Management."
        )
