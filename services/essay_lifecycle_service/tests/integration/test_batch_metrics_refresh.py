from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.implementations.batch_expectation import (
    BatchExpectation,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.metrics import get_metrics
from services.essay_lifecycle_service.models_db import Base


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_batch_metrics_updates_gauges() -> None:
    with PostgresContainer("postgres:15-alpine") as pg:
        pg_url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in pg_url:
            pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://")
        engine = create_async_engine(pg_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async_sessionmaker(engine, expire_on_commit=False)
        persistence = BatchTrackerPersistence(engine)

        # Create one GUEST active, one GUEST completed, and one REGULAR active
        guest_active = BatchExpectation(
            batch_id=str(uuid4()),
            expected_essay_ids=frozenset(["e1"]),
            expected_count=1,
            course_code=CourseCode.ENG5,
            essay_instructions="Write about environmental policy.",
            user_id="u1",
            org_id=None,
            correlation_id=uuid4(),
            created_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        await persistence.persist_batch_expectation(guest_active)

        guest_completed = BatchExpectation(
            batch_id=str(uuid4()),
            expected_essay_ids=frozenset(["e2"]),
            expected_count=1,
            course_code=CourseCode.ENG5,
            essay_instructions="Discuss the impact of urbanization.",
            user_id="u2",
            org_id=None,
            correlation_id=uuid4(),
            created_at=datetime.now(UTC) - timedelta(days=2),
            timeout_seconds=3600,
        )
        await persistence.persist_batch_expectation(guest_completed)
        await persistence.mark_batch_completed(guest_completed.batch_id)

        regular_active = BatchExpectation(
            batch_id=str(uuid4()),
            expected_essay_ids=frozenset(["e3"]),
            expected_count=1,
            course_code=CourseCode.ENG5,
            essay_instructions="Analyze modern poetry themes.",
            user_id="u3",
            org_id="org-1",
            correlation_id=uuid4(),
            created_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        await persistence.persist_batch_expectation(regular_active)

        # Refresh metrics
        await persistence.refresh_batch_metrics()

        metrics = get_metrics()
        active = metrics["batches_active"]
        completed = metrics["batches_completed"]

        # Extract values from Prometheus client
        def gauge_value(gauge: Any, class_type: str) -> float:
            # Collect samples and find matching label
            for metric in gauge.collect():
                for sample in metric.samples:
                    if sample.labels.get("class_type") == class_type:
                        return float(sample.value)
            return 0.0

        assert gauge_value(active, "GUEST") == 1.0
        assert gauge_value(completed, "GUEST") == 1.0
        assert gauge_value(active, "REGULAR") == 1.0
        assert gauge_value(completed, "REGULAR") == 0.0

        await engine.dispose()
