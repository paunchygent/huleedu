# TASK: Fix Anchor Essay Infrastructure

**Status**: NOT STARTED
**Priority**: HIGH
**Blocking**: End-to-end metadata passthrough testing
**Created**: 2025-11-13

---

## Problem Statement

End-to-end batch processing fails with RESOURCE_NOT_FOUND errors when retrieving anchor essays from Content Service.

### Symptoms
- Database contains 60 anchor essay references for assignment `00000000-0000-0000-0000-000000000001`
- Expected: Only 12 anchor essays (one per grade level)
- Batch processing fails when trying to retrieve content for IDs 1-48
- Only IDs 49-60 successfully retrieve content

### Root Cause
**Content Service uses ephemeral file storage that is lost on container restart.**

---

## Investigation Findings

### 1. Query Location and Logic

**File**: `services/cj_assessment_service/implementations/db_access_impl.py:563-589`

```python
async def get_anchor_essay_references(
    self,
    session: AsyncSession,
    assignment_id: str,
    grade_scale: str | None = None,
) -> list[Any]:
    stmt = select(AnchorEssayReference).where(
        AnchorEssayReference.assignment_id == assignment_id
    )

    if grade_scale:
        stmt = stmt.where(AnchorEssayReference.grade_scale == grade_scale)

    result = await session.execute(stmt)
    return list(result.scalars().all())
```

**Issues Identified**:
- No `ORDER BY` clause - returns records in arbitrary order
- No `LIMIT` clause - fetches ALL matching records
- No deduplication logic
- Simple filter by `assignment_id` and optionally `grade_scale`

**Called From**: `services/cj_assessment_service/cj_core_logic/batch_preparation.py:329`

---

### 2. Upload Mechanism

**File**: `services/cj_assessment_service/api/anchor_management.py:108-115`

```python
anchor_ref = AnchorEssayReference(
    assignment_id=register_request.assignment_id,
    grade=register_request.grade,
    grade_scale=grade_scale,
    text_storage_id=storage_id,
)
session.add(anchor_ref)  # ← ALWAYS CREATES NEW RECORD
await session.flush()
```

**Issues Identified**:
- Always uses INSERT - never updates existing records
- No unique constraint on database table
- No deduplication check before insertion

**Database Schema**:
```sql
Table: anchor_essay_references
Indexes:
    "anchor_essay_references_pkey" PRIMARY KEY, btree (id)
    "ix_anchor_essay_references_assignment_id" btree (assignment_id)
    "ix_anchor_essay_references_grade" btree (grade)
    "ix_anchor_essay_references_grade_scale" btree (grade_scale)

MISSING: UNIQUE constraint on (assignment_id, grade, grade_scale)
```

---

### 3. Upload Timeline (2025-11-13)

Five separate upload operations created 60 records:

| Batch | Time (UTC) | IDs Created | Status |
|-------|------------|-------------|--------|
| 1 | 14:24 | 1-12 | ❌ Content lost |
| 2 | 14:53 | 13-24 | ❌ Content lost |
| 3 | 14:55 | 25-36 | ❌ Content lost |
| 4 | 16:19 | 37-48 | ❌ Content lost |
| 5 | 18:36 | 49-60 | ✅ Content exists |

**Critical Event**: Content Service restarted at **18:35:47 UTC**

---

### 4. Content Service Storage Details

#### Current Implementation (MVP)
- **Type**: File-based ephemeral storage
- **Path**: `/app/.local_content_store_mvp/` (inside container)
- **Persistence**: NONE - data lost on container restart
- **Impact**: All content uploaded before 18:35:47 UTC was wiped

#### Evidence from Logs

**Valid Uploads (IDs 49-60, after restart)**:
```
2025-11-13 18:36:10 [info] Stored content with ID: 54c995dc26de42568d75b4e3a89c2295
2025-11-13 18:36:10 [info] Stored content with ID: 51e3cddb66f5434385ca055ec738eb46
2025-11-13 18:36:10 [info] Stored content with ID: 445767ddf050483e8aed7112f4d912c4
```

**Failed Retrievals (IDs 1-48, before restart)**:
```
2025-11-13 18:37:45 [warning] Content download failed: content with ID 'f54e560cb23c4e69985f3d90c621f8f4' not found
2025-11-13 18:37:45 [warning] Content download failed: content with ID '67fbdbc9adae449ead3708b72717998c' not found
```

#### Storage ID Validity

| ID Range | Upload Time | Storage ID Example | Valid? | Reason |
|----------|-------------|-------------------|--------|--------|
| 1-12 | 14:24 (4h before restart) | f54e560cb23c4e69985f3d90c621f8f4 | ❌ | Pre-restart |
| 13-24 | 14:53 (3.7h before restart) | 3b5a9c3c53964e8a837271bd0eb7bfb7 | ❌ | Pre-restart |
| 25-36 | 14:55 (3.6h before restart) | e2a07e22ec504cf8886552256966daaf | ❌ | Pre-restart |
| 37-48 | 16:19 (2.3h before restart) | 5391cc20da3e4ca0aca41e3c478e1144 | ❌ | Pre-restart |
| 49-60 | 18:36 (23s after restart) | 54c995dc26de42568d75b4e3a89c2295 | ✅ | Post-restart |

---

## Implementation Plan

### Phase 1: Migrate Content Service to Database-Backed Storage

**Objective**: Replace ephemeral file storage with PostgreSQL-backed storage following established patterns

**Pattern Reference**: `services/file_service/` for database storage implementation

#### 1.1: Create Database Model

**File**: `services/content_service/models_db.py` (NEW)

**Pattern**: Based on `services/file_service/models_db.py`

**Content**:
```python
"""SQLAlchemy models for Content Service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class StoredContent(Base):
    """Model for storing content data in PostgreSQL."""

    __tablename__ = "stored_content"

    # Primary key - use content_id as string (UUID hex)
    content_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        comment="UUID hex string identifying the content"
    )

    # Content data
    content_data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Raw content bytes"
    )

    # Metadata
    content_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Size of content in bytes"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,  # ← Index for time-based queries
        comment="When content was stored"
    )

    # Tracing
    correlation_id: Mapped[Optional[UUID]] = mapped_column(  # ← Optional
        PostgresUUID(as_uuid=True),
        nullable=True,  # ← nullable=True for consistency
        comment="Correlation ID for request tracing"
    )
```

#### 1.2: Create Repository Protocol

**File**: `services/content_service/protocols.py`

**Pattern**: Based on `services/file_service/protocols.py` - FileRepositoryProtocol

**Add**:
```python
from typing import Protocol
from uuid import UUID


class ContentRepositoryProtocol(Protocol):
    """Protocol for content persistence operations."""

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        correlation_id: UUID | None = None
    ) -> None:
        """
        Store content in database.

        Args:
            content_id: UUID hex string for content identifier
            content_data: Raw bytes to store
            correlation_id: Optional correlation ID for tracing

        Note:
            Repository manages its own sessions internally.
        """
        ...

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None
    ) -> bytes:
        """
        Retrieve content from database.

        Args:
            content_id: UUID hex string for content identifier
            correlation_id: Optional correlation ID for tracing

        Returns:
            Raw content bytes

        Raises:
            HuleEduError: If content not found (via raise_resource_not_found)

        Note:
            Repository manages its own sessions internally.
        """
        ...

    async def content_exists(
        self,
        content_id: str
    ) -> bool:
        """
        Check if content exists.

        Args:
            content_id: UUID hex string for content identifier

        Returns:
            True if content exists, False otherwise

        Note:
            Repository manages its own sessions internally.
        """
        ...
```

#### 1.3: Implement Database Repository

**File**: `services/content_service/implementations/content_repository_impl.py` (NEW)

**Pattern**: Based on `services/file_service/implementations/file_repository_impl.py`

**Content**:
```python
"""Repository implementation for Content Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

from huleedu_service_libs.error_handling import raise_resource_not_found
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.content_service.models_db import StoredContent
from services.content_service.protocols import ContentRepositoryProtocol

logger = create_service_logger("content_service.repository")


class ContentRepository(ContentRepositoryProtocol):
    """Repository implementation for Content Service with database persistence."""

    def __init__(self, engine: AsyncEngine) -> None:
        """
        Initialize the repository with a database engine.

        Args:
            engine: SQLAlchemy async engine for database operations
        """
        self._engine = engine
        self._sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Initialized content repository")

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session with proper cleanup."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        correlation_id: UUID | None = None
    ) -> None:
        """
        Store content in database.

        Args:
            content_id: UUID hex string for content identifier
            content_data: Raw bytes to store
            correlation_id: Optional correlation ID for tracing
        """
        async with self._get_session() as session:
            stored_content = StoredContent(
                content_id=content_id,
                content_data=content_data,
                content_size=len(content_data),
                correlation_id=correlation_id,
            )
            session.add(stored_content)

            logger.info(
                f"Stored content with ID: {content_id}",
                extra={
                    "content_id": content_id,
                    "content_size": len(content_data),
                    "correlation_id": str(correlation_id) if correlation_id else None,
                },
            )

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None
    ) -> bytes:
        """
        Retrieve content from database.

        Args:
            content_id: UUID hex string for content identifier
            correlation_id: Optional correlation ID for tracing

        Returns:
            Raw content bytes

        Raises:
            HuleEduError: If content not found
        """
        async with self._get_session() as session:
            stmt = select(StoredContent).where(StoredContent.content_id == content_id)
            result = await session.execute(stmt)
            stored_content = result.scalar_one_or_none()

            if not stored_content:
                logger.warning(
                    f"Content not found for ID: {content_id}",
                    extra={"correlation_id": str(correlation_id) if correlation_id else None},
                )
                raise_resource_not_found(
                    service="content_service",
                    operation="get_content",
                    resource_type="content",
                    resource_id=content_id,
                    correlation_id=correlation_id,
                )

            return stored_content.content_data

    async def content_exists(
        self,
        content_id: str
    ) -> bool:
        """
        Check if content exists.

        Args:
            content_id: UUID hex string for content identifier

        Returns:
            True if content exists, False otherwise
        """
        async with self._get_session() as session:
            stmt = select(StoredContent.content_id).where(
                StoredContent.content_id == content_id
            )
            result = await session.execute(stmt)
            exists = result.scalar_one_or_none() is not None

            logger.debug(
                f"Content exists check for ID {content_id}: {exists}",
                extra={"content_id": content_id},
            )

            return exists
```

#### 1.4: Create Mock Repository for Tests

**File**: `services/content_service/implementations/mock_content_repository.py` (NEW)

**Pattern**: Dict-based in-memory mock (similar to Essay Lifecycle mock pattern)

**Content**:
```python
"""Mock repository for testing Content Service."""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.error_handling import raise_resource_not_found
from huleedu_service_libs.logging_utils import create_service_logger

from services.content_service.protocols import ContentRepositoryProtocol

logger = create_service_logger("content_service.repository.mock")


class MockContentRepository(ContentRepositoryProtocol):
    """In-memory mock implementation for testing."""

    def __init__(self) -> None:
        """Initialize mock repository with empty storage."""
        self.content_store: dict[str, bytes] = {}
        logger.info("Initialized mock content repository")

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        correlation_id: UUID | None = None
    ) -> None:
        """Store content in memory."""
        self.content_store[content_id] = content_data
        logger.debug(f"Stored content {content_id} in mock")

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None
    ) -> bytes:
        """Retrieve content from memory."""
        if content_id not in self.content_store:
            raise_resource_not_found(
                service="content_service",
                operation="get_content",
                resource_type="content",
                resource_id=content_id,
                correlation_id=correlation_id,
            )
        return self.content_store[content_id]

    async def content_exists(
        self,
        content_id: str
    ) -> bool:
        """Check if content exists in memory."""
        return content_id in self.content_store
```

#### 1.5: Update DI Configuration

**File**: `services/content_service/di.py`

**Pattern**: Based on `services/file_service/di.py` lines 134-170

**Changes**:
```python
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from dishka import Provider, Scope, provide

from services.content_service.protocols import ContentRepositoryProtocol
from services.content_service.implementations.content_repository_impl import ContentRepository


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies."""

    @provide(scope=Scope.APP)
    async def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide async database engine for Content Service."""
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,  # Set to True for SQL debugging
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
        )
        return engine

    @provide(scope=Scope.APP)
    def provide_content_repository(
        self,
        engine: AsyncEngine,
    ) -> ContentRepositoryProtocol:
        """Provide content repository implementation."""
        return ContentRepository(engine)
```

#### 1.6: Update Content Routes

**File**: `services/content_service/api/content_routes.py`

**Pattern**: Inject repository protocol only (NO session injection)

**Changes**:
```python
from dishka.integrations.quart import FromDishka

from services.content_service.protocols import ContentRepositoryProtocol


@content_bp.route("", methods=["POST"])
@inject
async def upload_content(
    repository: FromDishka[ContentRepositoryProtocol],  # ← Only protocol
    metrics: FromDishka[ContentMetricsProtocol],
) -> Response | tuple[Response, int]:
    """
    Upload content endpoint.

    Repository manages its own sessions internally.
    """
    # ... existing request parsing ...

    # Call repository method - it handles session lifecycle
    content_id = uuid.uuid4().hex
    await repository.save_content(
        content_id=content_id,
        content_data=content_bytes,
        correlation_id=correlation_id
    )

    # ... return response ...


@content_bp.route("/<content_id>", methods=["GET"])
@inject
async def get_content(
    content_id: str,
    repository: FromDishka[ContentRepositoryProtocol],  # ← Only protocol
    metrics: FromDishka[ContentMetricsProtocol],
) -> Response | tuple[Response, int]:
    """
    Retrieve content endpoint.

    Repository manages its own sessions internally.
    """
    # Call repository method - it handles session lifecycle
    content_data = await repository.get_content(
        content_id=content_id,
        correlation_id=correlation_id
    )

    # ... return response ...
```

#### 1.7: Create Alembic Migration

**Directory**: `services/content_service/alembic/` (setup if not exists)

**Migration**: Create `stored_content` table

**Pattern**: Based on `.claude/rules/085-database-migration-standards.md`

**Commands**:
```bash
cd services/content_service

# Initialize alembic (first time only)
pdm run alembic init alembic
# Then edit alembic.ini and alembic/env.py to reference models_db

# Create migration
pdm run alembic revision --autogenerate -m "Create stored_content table"

# Review the generated migration file

# Restart services with new database
pdm run dev-build-start content_service  # Or dev-restart if already running

# Apply migration
pdm run alembic upgrade head

# Verify migration applied
pdm run alembic current
```

#### 1.8: Update Docker Compose

**File**: `docker-compose.infrastructure.yml`

**Pattern**: Based on file_service_db configuration (infrastructure.yml lines 90-107)

**Add**:
```yaml
content_service_db:
  image: postgres:15
  container_name: huleedu_content_service_db
  restart: unless-stopped
  networks:
    - huleedu_internal_network
  ports:
    - "5445:5432"  # Port 5445 (5440 used by nlp_db)
  environment:
    - POSTGRES_DB=huleedu_content
    - POSTGRES_USER=${HULEEDU_DB_USER}
    - POSTGRES_PASSWORD=${HULEEDU_DB_PASSWORD}
  volumes:
    - content_service_db_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${HULEEDU_DB_USER} -d huleedu_content"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
```

**Update content_service section**:
```yaml
content_service:
  depends_on:
    - content_service_db  # ← Correct reference
  environment:
    # ... existing env vars ...
```

**Add to docker-compose.yml volumes section**:
```yaml
volumes:
  content_service_db_data:
```

#### 1.9: Update Config

**File**: `services/content_service/config.py`

**Pattern**: Based on `services/file_service/config.py` lines 12-18, 103-123

**Add at module level (top of file)**:
```python
from dotenv import find_dotenv, load_dotenv

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))
```

**Add to Settings class**:
```python
from huleedu_service_libs.config import SecureServiceSettings


class Settings(SecureServiceSettings):
    """Configuration settings for Content Service."""

    # ... existing settings ...

    @property
    def DATABASE_URL(self) -> str:
        """Return the PostgreSQL database URL for both runtime and migrations."""
        import os

        env_type = os.getenv("ENV_TYPE", "development").lower()
        if env_type == "docker":
            dev_host = os.getenv("CONTENT_SERVICE_DB_HOST", "content_service_db")
            dev_port_str = os.getenv("CONTENT_SERVICE_DB_PORT", "5432")
        else:
            dev_host = "localhost"
            dev_port_str = "5445"  # External port (5440 used by nlp_db)

        dev_port = int(dev_port_str)

        return self.build_database_url(
            database_name="huleedu_content",
            service_env_var_prefix="CONTENT_SERVICE",
            dev_port=dev_port,
            dev_host=dev_host,
        )


# Create a single instance for the application to use
settings = Settings()
```

#### 1.10: Testing

**Sequence**:
1. Build and start services with new database:
   ```bash
   pdm run dev-build-start content_service
   ```

2. Run database migration:
   ```bash
   cd services/content_service
   pdm run alembic upgrade head
   pdm run alembic current  # Verify
   ```

3. Upload test content via API:
   ```bash
   curl -X POST http://localhost:8001/v1/content \
     -H "Content-Type: application/json" \
     -d '{"content": "test content for persistence", "metadata": {}}'
   ```

4. Verify content stored in database:
   ```bash
   source .env
   docker exec huleedu_content_service_db psql -U "$HULEEDU_DB_USER" -d huleedu_content \
     -c "SELECT content_id, content_size, created_at FROM stored_content;"
   ```

5. Restart Content Service:
   ```bash
   pdm run dev-restart content_service
   ```

6. Retrieve same content via API (use content_id from step 3):
   ```bash
   curl http://localhost:8001/v1/content/{content_id}
   ```

**Expected**: Content still accessible after restart (proves persistence)

---

### Phase 2: Database Cleanup

**Objective**: Remove stale anchor references pointing to lost content

**Action**: Execute SQL cleanup
```sql
DELETE FROM anchor_essay_references
WHERE assignment_id = '00000000-0000-0000-0000-000000000001'
AND id < 49;
```

**Command**:
```bash
source .env
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c "DELETE FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001' AND id < 49;"
```

**Verification**:
```bash
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c "SELECT COUNT(*), MIN(id), MAX(id) FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001';"
```

Expected: `COUNT=12, MIN=49, MAX=60`

---

### Phase 3: Add Database Unique Constraint

**Objective**: Prevent future duplicate anchor uploads

**Action**: Create Alembic migration

**File**: `services/cj_assessment_service/alembic/versions/YYYYMMDD_add_anchor_unique_constraint.py`

**Migration SQL**:
```sql
ALTER TABLE anchor_essay_references
ADD CONSTRAINT uq_anchor_assignment_grade_scale
UNIQUE (assignment_id, grade, grade_scale);
```

**Commands**:
```bash
# Create migration
cd services/cj_assessment_service
../../.venv/bin/alembic revision -m "Add unique constraint to anchor_essay_references"

# Apply migration
pdm run dev-restart cj_assessment_service
```

**Testing**:
- Attempt to upload duplicate anchor for same assignment/grade
- Should fail with constraint violation error

---

### Phase 4: Implement Upsert Logic in API

**Objective**: Update existing anchors instead of creating duplicates

**File**: `services/cj_assessment_service/api/anchor_management.py:108-115`

**Current Code**:
```python
anchor_ref = AnchorEssayReference(
    assignment_id=register_request.assignment_id,
    grade=register_request.grade,
    grade_scale=grade_scale,
    text_storage_id=storage_id,
)
session.add(anchor_ref)
await session.flush()
```

**New Code** (using SQLAlchemy upsert):
```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(AnchorEssayReference).values(
    assignment_id=register_request.assignment_id,
    grade=register_request.grade,
    grade_scale=grade_scale,
    text_storage_id=storage_id,
)

stmt = stmt.on_conflict_do_update(
    constraint='uq_anchor_assignment_grade_scale',
    set_={'text_storage_id': storage_id}
)

await session.execute(stmt)
await session.flush()
```

**Testing**:
1. Upload 12 anchor essays
2. Upload same 12 anchor essays again
3. Verify database still contains exactly 12 records (not 24)
4. Verify `text_storage_id` values updated to latest uploads

---

## Files to Modify

### Phase 1: Content Service Database Migration
1. `services/content_service/models_db.py` - NEW: Database model
2. `services/content_service/protocols.py` - Add ContentRepositoryProtocol
3. `services/content_service/implementations/content_repository_impl.py` - NEW: DB repository
4. `services/content_service/implementations/mock_content_repository.py` - NEW: Mock for tests
5. `services/content_service/di.py` - Wire up repository and session
6. `services/content_service/api/content_routes.py` - Use repository instead of file store
7. `services/content_service/config.py` - Add DATABASE_URL
8. `services/content_service/alembic/` - Initialize and create migration
9. `docker-compose.dev.yml` - Add content_db service and volume

### Phase 2: Anchor Cleanup
10. SQL cleanup via docker exec

### Phase 3: CJ Assessment Constraint
11. `services/cj_assessment_service/alembic/versions/[NEW]` - Unique constraint migration

### Phase 4: CJ Assessment Upsert
12. `services/cj_assessment_service/api/anchor_management.py:108-115` - Upsert logic

---

## Testing Plan

### After Phase 1 (Persistence)
```bash
# Upload test content
curl -X POST http://localhost:8001/v1/content \
  -H "Content-Type: application/json" \
  -d '{"content": "test", "metadata": {}}'

# Note the storage_id from response

# Restart Content Service
pdm run dev-restart content_service

# Verify content still exists
curl http://localhost:8001/v1/content/{storage_id}
```

### After Phase 2 (Cleanup)
```bash
# Run batch processing test
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode execute \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --course-id 00000000-0000-0000-0000-000000000002 \
  --batch-id test-cleanup-$(date +%Y%m%d-%H%M) \
  --max-comparisons 5 \
  --kafka-bootstrap localhost:9093 \
  --await-completion \
  --completion-timeout 30 \
  --verbose
```

Expected: No RESOURCE_NOT_FOUND errors

### After Phase 3 (Constraint)
```bash
# Try to upload duplicate anchor (should fail)
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode register-anchors \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --anchors scripts/cj_experiments_runners/eng5_np/data/eng5_np_anchor_essays.json
```

Expected: Database constraint violation error

### After Phase 4 (Upsert)
```bash
# Upload anchors twice (should succeed with updates)
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode register-anchors \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --anchors scripts/cj_experiments_runners/eng5_np/data/eng5_np_anchor_essays.json

# Verify still only 12 records
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c "SELECT COUNT(*) FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001';"
```

Expected: COUNT=12 (not 24)

---

## Success Criteria

- ✅ Content Service storage persists across container restarts
- ✅ Database contains exactly 12 anchor references for test assignment
- ✅ All anchor storage IDs valid in Content Service
- ✅ Batch processing completes without RESOURCE_NOT_FOUND errors
- ✅ Database constraint prevents duplicate anchors
- ✅ Re-uploading anchors updates existing records (no duplicates)
- ✅ End-to-end metadata passthrough test passes

---

## Related Tasks

- `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` - Metadata passthrough implementation (COMPLETE)
- This task unblocks end-to-end testing of metadata passthrough feature

---

## Notes

- CJ Assessment DB was reset on 2025-11-13, so all 60 records were created same day
- The duplicate upload issue is a workflow problem (manual re-uploads), not a code bug
- However, the code should handle this gracefully with upsert logic
- Content Service restart was the triggering event that exposed the storage issue
- Root cause: Content Service used ephemeral file storage instead of persistent database
- Solution: Migrate to PostgreSQL-backed storage following established File Service pattern
- Benefits: Transactional consistency, backup integration, no volume mount dependencies
