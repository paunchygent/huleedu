---
inclusion: fileMatch
fileMatchPattern: "**/models/**,**/repositories/**,**/migrations/**"
---

# Database Patterns and Standards

## SQLAlchemy Model Patterns

### Base Model Structure
```python
from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### Entity Model Examples
```python
class Essay(BaseModel):
    __tablename__ = "essays"
    
    content_id = Column(String(255), nullable=False, unique=True)
    text_storage_id = Column(String(255), nullable=True)
    language = Column(String(2), nullable=False, default="en")
    status = Column(String(50), nullable=False, default="pending")
    metadata = Column(Text, nullable=True)  # JSON stored as text
    
    # Relationships
    batch_id = Column(UUID(as_uuid=True), ForeignKey("batches.id"))
    batch = relationship("Batch", back_populates="essays")
```

## Repository Pattern Implementation

### Protocol Definition
```python
from typing import Protocol, Optional, List
from uuid import UUID

class EssayRepositoryProtocol(Protocol):
    async def create(self, essay: Essay) -> Essay:
        """Create a new essay record."""
        ...
    
    async def get_by_id(self, essay_id: UUID) -> Optional[Essay]:
        """Retrieve essay by ID."""
        ...
    
    async def update(self, essay: Essay) -> Essay:
        """Update existing essay."""
        ...
    
    async def get_by_batch_id(self, batch_id: UUID) -> List[Essay]:
        """Get all essays in a batch."""
        ...
```

### Repository Implementation
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

class EssayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, essay: Essay) -> Essay:
        try:
            self.session.add(essay)
            await self.session.commit()
            await self.session.refresh(essay)
            
            logger.info(
                "Essay created successfully",
                extra={"essay_id": str(essay.id)}
            )
            return essay
        except Exception as e:
            await self.session.rollback()
            logger.error(
                "Failed to create essay",
                extra={"error": str(e)},
                exc_info=True
            )
            raise
    
    async def get_by_id(self, essay_id: UUID) -> Optional[Essay]:
        stmt = select(Essay).where(Essay.id == essay_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

## Database Connection Management

### Async Database Setup
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def get_session(self) -> AsyncSession:
        return self.session_factory()
    
    async def close(self):
        await self.engine.dispose()
        logger.info("Database connections closed")
```

## Migration Patterns

### Alembic Configuration
```python
# alembic/env.py
from alembic import context
from sqlalchemy import engine_from_config, pool
from models import Base  # Import your models

def run_migrations_online():
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata
        )

        with context.begin_transaction():
            context.run_migrations()
```

### Migration Best Practices
- Always review generated migrations before applying
- Use descriptive migration messages
- Test migrations on development data first
- Create rollback procedures for complex changes
- Never modify existing migrations after deployment

## Transaction Management

### Service-Level Transactions
```python
from contextlib import asynccontextmanager

class EssayService:
    def __init__(self, repository: EssayRepositoryProtocol, db_manager: DatabaseManager):
        self.repository = repository
        self.db_manager = db_manager
    
    @asynccontextmanager
    async def transaction(self):
        session = await self.db_manager.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def process_batch_essays(self, batch_id: UUID, essays_data: List[dict]):
        async with self.transaction() as session:
            repository = EssayRepository(session)
            
            for essay_data in essays_data:
                essay = Essay(**essay_data, batch_id=batch_id)
                await repository.create(essay)
```

## Testing Database Patterns

### Test Database Setup
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
async def test_database():
    # Use PostgreSQL container for integration tests
    with PostgresContainer("postgres:15") as postgres:
        database_url = postgres.get_connection_url().replace("psycopg2", "asyncpg")
        
        engine = create_async_engine(database_url)
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        yield database_url
        
        await engine.dispose()

@pytest.fixture
async def db_session(test_database):
    engine = create_async_engine(test_database)
    session = AsyncSession(engine)
    
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
```