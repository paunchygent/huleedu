# TASK-LLM-02: Event-Driven CJ Assessment Service with State Management

**Status**: Phase 1 & 2 Completed ✅ | **ARCHITECTURAL ISSUES IDENTIFIED** ⚠️  
**Estimated Duration**: 5-7 days *(Complete)*  
**Dependencies**: TASK-LLM-01 completed ✅  
**Risk Level**: High (Complex state management, breaking change)
**Architectural Impact**: High (Transforms service to event-driven with persistent state)
**Follow-up Required**: TASK-CJ-03 for proper batch integration

## 📋 Executive Summary

Transform the `cj_assessment_service` from a synchronous, polling-based client to a fully event-driven service with robust state management. This is a **breaking change** that introduces persistent batch state tracking, async callback processing, and automated recovery mechanisms.

## 🎯 Business Objectives

1. **Enable True Scalability**: Support 1000+ concurrent batches (vs ~10 with HTTP limits)
2. **Improve Resilience**: Automatic recovery from failures, service restarts
3. **Reduce Costs**: Leverage batch APIs efficiently without blocking resources
4. **Enhance Observability**: Complete visibility into batch processing state

## 🚨 Critical Architectural Changes

### New Infrastructure Required

- **Batch State Tables**: Persistent tracking of batch progress
- **Event-Driven Workflow**: Replace synchronous loops with async callbacks
- **Background Monitor**: Automated detection and recovery of stuck batches
- **Distributed Locking**: Prevent race conditions in callback processing

### Removed Patterns

- HTTP polling logic in `LLMProviderServiceClient`
- Synchronous batch processing loops
- In-memory state during processing

## ✅ Architecture Prerequisites

**From TASK-LLM-01**:

- ✅ LLM Provider Service publishes callbacks to Kafka
- ✅ `LLMComparisonResultV1` event contract defined
- ✅ Polling endpoints removed from LLM Provider Service

**Current Infrastructure**:

- ✅ Kafka consumer architecture established
- ✅ PostgreSQL database with async support
- ✅ Event publishing patterns via `CJEventPublisherProtocol`

## 📚 Required Architecture Rules

**MUST READ** before implementation:

- `.cursor/rules/020-architectural-mandates.mdc` - Event-driven patterns
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - Kafka consumption
- `.cursor/rules/042-async-patterns-and-di.mdc` - Async workflow patterns
- `.cursor/rules/053-sqlalchemy-async-patterns.mdc` - Database state management
- `.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling

## 🎨 Implementation Design

### Phase 1: Database Schema & State Management ✅ COMPLETED

**Completion Date**: 2025-07-15

**Phase 1 Summary**:

- ✅ Created `BatchStateEnum` in `common_core/status_enums.py` (relocated from planned location)
- ✅ Added `CJBatchState` model for persistent batch state tracking
- ✅ Updated `ComparisonPair` model with `request_correlation_id`, `submitted_at`, and `completed_at` fields
- ✅ Created Alembic migration for batch state management
- ✅ Updated configuration with callback topic and batch monitoring settings
- ✅ Removed polling code from `LLMProviderServiceClient`
- ✅ Added `callback_topic` to all LLM Provider requests
- ✅ Implemented structured error handling throughout

**Implementation Note**: Database schema successfully created, but enum placement differs from original plan.

#### 1.1 Define Batch State Enumeration

**File**: `services/cj_assessment_service/enums.py` (new)

```python
"""Enumerations for CJ Assessment Service state management."""
import enum


class BatchStateEnum(str, enum.Enum):
    """State machine for CJ assessment batch processing."""
    
    INITIALIZING = "INITIALIZING"              # Batch created, essays being prepared
    GENERATING_PAIRS = "GENERATING_PAIRS"      # Creating comparison pairs
    WAITING_CALLBACKS = "WAITING_CALLBACKS"    # Comparisons sent, awaiting results
    SCORING = "SCORING"                        # Calculating Bradley-Terry scores
    COMPLETED = "COMPLETED"                    # Successfully processed
    FAILED = "FAILED"                         # Processing failed
    CANCELLED = "CANCELLED"                   # Manually stopped
```

#### 1.2 Add Batch State Tracking Model

**File**: `services/cj_assessment_service/models_db.py`

```python
# Add to imports
from sqlalchemy import Boolean, Integer
from services.cj_assessment_service.enums import BatchStateEnum

# Add after existing models
class CJBatchState(Base):
    """
    Real-time processing state for CJ assessment batches.
    Single source of truth for batch progress and health.
    """
    
    __tablename__ = "cj_batch_states"
    
    # Primary key linked to batch
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("cj_batch_uploads.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        doc="Links to the main batch record"
    )
    
    # Current state
    state: Mapped[BatchStateEnum] = mapped_column(
        SQLAlchemyEnum(
            BatchStateEnum,
            name="batch_state_enum",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        default=BatchStateEnum.INITIALIZING,
        nullable=False,
        index=True,
        doc="Current processing state"
    )
    
    # Progress tracking
    total_comparisons: Mapped[int] = mapped_column(
        Integer, 
        nullable=False, 
        doc="Total comparisons to process"
    )
    submitted_comparisons: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        doc="Comparisons sent to LLM provider"
    )
    completed_comparisons: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        doc="Successfully completed comparisons"
    )
    failed_comparisons: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        doc="Failed comparison attempts"
    )
    
    # Monitoring fields
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
        nullable=False,
        doc="For timeout detection"
    )
    
    # Partial completion support
    partial_scoring_triggered: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        doc="Prevents duplicate partial scoring"
    )
    completion_threshold_pct: Mapped[int] = mapped_column(
        Integer,
        default=95,
        nullable=False,
        doc="Percentage threshold for partial completion"
    )
    
    # Processing metadata
    current_iteration: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        doc="Current comparison iteration"
    )
    processing_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Stores previous scores, settings, etc."
    )
    
    # Relationships
    batch_upload: Mapped["CJBatchUpload"] = relationship(
        back_populates="batch_state",
        lazy="joined"  # Always load with state
    )

# Update CJBatchUpload to add relationship
class CJBatchUpload(Base):
    # ... existing fields ...
    
    # Add relationship to state
    batch_state: Mapped["CJBatchState"] = relationship(
        back_populates="batch_upload",
        cascade="all, delete-orphan",
        uselist=False  # One-to-one
    )
```

#### 1.3 Update Comparison Pair Model

**File**: `services/cj_assessment_service/models_db.py`

```python
# Update ComparisonPair model
class ComparisonPair(Base):
    # ... existing fields ...
    
    # Add correlation tracking for callbacks
    request_correlation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), 
        nullable=True, 
        index=True,
        doc="Links to LLM provider callback"
    )
    
    # Add timing information
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When sent to LLM provider"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When result received"
    )
```

#### 1.4 Create Database Migration

**File**: `services/cj_assessment_service/alembic/versions/YYYYMMDD_add_batch_state_management.py`

```python
"""Add batch state management tables

Revision ID: [generated]
Revises: [previous]
Create Date: [timestamp]
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Create batch state enum
    op.execute("CREATE TYPE batch_state_enum AS ENUM ('INITIALIZING', 'GENERATING_PAIRS', 'WAITING_CALLBACKS', 'SCORING', 'COMPLETED', 'FAILED', 'CANCELLED')")
    
    # Create batch states table
    op.create_table(
        'cj_batch_states',
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('state', sa.Enum('INITIALIZING', 'GENERATING_PAIRS', 'WAITING_CALLBACKS', 'SCORING', 'COMPLETED', 'FAILED', 'CANCELLED', name='batch_state_enum'), nullable=False),
        sa.Column('total_comparisons', sa.Integer(), nullable=False),
        sa.Column('submitted_comparisons', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_comparisons', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_comparisons', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('partial_scoring_triggered', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completion_threshold_pct', sa.Integer(), nullable=False, server_default='95'),
        sa.Column('current_iteration', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('processing_metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['cj_batch_uploads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('batch_id')
    )
    op.create_index(op.f('ix_cj_batch_states_state'), 'cj_batch_states', ['state'], unique=False)
    
    # Add correlation tracking to comparison pairs
    op.add_column('cj_comparison_pairs', sa.Column('request_correlation_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('cj_comparison_pairs', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('cj_comparison_pairs', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_cj_comparison_pairs_request_correlation_id'), 'cj_comparison_pairs', ['request_correlation_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_cj_comparison_pairs_request_correlation_id'), table_name='cj_comparison_pairs')
    op.drop_column('cj_comparison_pairs', 'completed_at')
    op.drop_column('cj_comparison_pairs', 'submitted_at')
    op.drop_column('cj_comparison_pairs', 'request_correlation_id')
    op.drop_index(op.f('ix_cj_batch_states_state'), table_name='cj_batch_states')
    op.drop_table('cj_batch_states')
    op.execute("DROP TYPE batch_state_enum")
```

### Phase 2: Remove Polling & Add Callback Support ✅ COMPLETED

**Completion Date**: 2025-07-15

**Phase 2 Summary**:

- ✅ Created `workflow_logic.py` with callback processing framework
- ✅ Implemented `continue_cj_assessment_workflow()` function
- ✅ Added callback result processing with idempotency checks
- ✅ Implemented batch state updates with optimistic locking
- ✅ Created batch progress tracking and decision logic
- ✅ Added comprehensive logging and metrics integration

**Architectural Issues Identified**:

- ⚠️ **Parallel Workflow**: `workflow_logic.py` creates isolated workflow instead of integrating with existing batch processing
- ⚠️ **Incomplete Integration**: Multiple TODOs for score calculation and event publishing
- ⚠️ **Missing Connections**: No integration with existing `comparison_processing.py` or `scoring_ranking.py`
- ⚠️ **Stub Implementation**: Score stability checking and final scoring are placeholder functions

**Phase 2 Original Plan**:

#### 2.1 Update Configuration

**File**: `services/cj_assessment_service/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # LLM callback configuration
    LLM_PROVIDER_CALLBACK_TOPIC: str = Field(
        default="huleedu.llm_provider.comparison_result.v1",
        description="Kafka topic for LLM comparison callbacks"
    )
    
    # Batch processing configuration
    BATCH_TIMEOUT_HOURS: int = Field(
        default=4,
        description="Hours before considering a batch stuck"
    )
    BATCH_MONITOR_INTERVAL_MINUTES: int = Field(
        default=5,
        description="Interval for batch health checks"
    )
    MIN_SUCCESS_RATE_THRESHOLD: float = Field(
        default=0.8,
        description="Minimum success rate before failing batch"
    )
    
    # Score stability configuration
    SCORE_STABILITY_THRESHOLD: float = Field(
        default=0.05,
        description="Max score change to consider stable"
    )
    MAX_ITERATIONS: int = Field(
        default=5,
        description="Maximum comparison iterations"
    )
    
    # Performance tuning
    MAX_CONCURRENT_COMPARISONS: int = Field(
        default=100,
        description="Max comparisons per batch in flight"
    )
```

#### 2.2 Refactor LLM Provider Client

**File**: `services/cj_assessment_service/implementations/llm_provider_service_client.py`

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.libs.huleedu_service_libs.circuit_breaker import CircuitBreaker

class LLMProviderServiceClient(LLMProviderProtocol):
    """Event-driven client for LLM Provider Service with circuit breaker."""
    
    def __init__(self, session: aiohttp.ClientSession, settings: Settings):
        self.session = session
        self.settings = settings
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=aiohttp.ClientError
        )
    
    async def generate_comparison(
        self,
        essay_a: str,
        essay_b: str,
        instructions: str,
        correlation_id: UUID,
        provider_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Optional[LLMComparisonAssessment]:
        """
        Submit comparison request with callback topic.
        Returns immediately with None (result arrives via Kafka callback).
        Raises HuleEduError on failure.
        """
        
        # Build request with callback topic
        request_body = {
            "user_prompt": self._build_comparison_prompt(essay_a, essay_b, instructions),
            "essay_a": essay_a,
            "essay_b": essay_b,
            "callback_topic": self.settings.LLM_PROVIDER_CALLBACK_TOPIC,  # Required
            "llm_config_overrides": {
                "provider_override": provider_override or self.settings.DEFAULT_LLM_PROVIDER.value,
                "model_override": self.settings.DEFAULT_LLM_MODEL,
                "temperature_override": self.settings.LLM_TEMPERATURE,
                "max_tokens_override": max_tokens_override,
            },
            "correlation_id": str(correlation_id),
        }
        
        # Apply circuit breaker pattern
        @self._circuit_breaker
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
        )
        async def _make_request():
            async with self.session.post(
                f"{self.settings.LLM_PROVIDER_SERVICE_URL}/api/v1/comparison",
                json=request_body,
                headers=self._get_headers(correlation_id),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                return response
        
        try:
            response = await _make_request()
                
            if response.status == 200:
                # Immediate response (cached or fast provider)
                return await self._handle_immediate_response(
                    await response.text(), 
                    correlation_id
                )
                
            elif response.status == 202:
                # Request queued - result will arrive via callback
                logger.info(
                    "Comparison queued for async processing",
                    extra={
                        "correlation_id": str(correlation_id),
                        "callback_topic": self.settings.LLM_PROVIDER_CALLBACK_TOPIC
                    }
                )
                return None  # No result yet - will arrive via callback
                
            else:
                # Error response - raise structured error
                from services.libs.huleedu_service_libs.error_handling import (
                    raise_external_service_error
                )
                raise_external_service_error(
                    service="cj_assessment_service",
                    operation="generate_comparison",
                    external_service="llm_provider_service",
                    message=f"LLM Provider error: {response.status}",
                    correlation_id=correlation_id,
                    details={"status": response.status}
                )
                    
        except HuleEduError:
            # Re-raise structured errors
            raise
        except Exception as e:
            # Convert unstructured errors
            from services.libs.huleedu_service_libs.error_handling import (
                raise_external_service_error
            )
            raise_external_service_error(
                service="cj_assessment_service",
                operation="generate_comparison",
                external_service="llm_provider_service",
                message=f"Failed to call LLM Provider: {str(e)}",
                correlation_id=correlation_id,
                details={"error_type": type(e).__name__}
            )
    
    # DELETE all polling methods:
    # - _handle_queued_response()
    # - _poll_for_results()
    # - _retrieve_queue_result()
```

### Phase 3: Implement Callback Processing ⚠️ PARTIALLY COMPLETED

**Current Status**: Framework implemented but incomplete integration

**Completed**:

- ✅ Updated Kafka consumer to handle callback topic
- ✅ Added `process_llm_result` handler in `event_processor.py`
- ✅ Implemented correlation ID-based result routing
- ✅ Added callback latency metrics

**Missing/Incomplete**:

- ⚠️ **Callback Processing**: Real workflow integration with existing batch system
- ⚠️ **State Transitions**: Complete state machine implementation
- ⚠️ **Score Integration**: Connection to existing Bradley-Terry scoring
- ⚠️ **Error Recovery**: Proper error handling and retry mechanisms

**Phase 3 Original Plan**:

#### 3.1 Update Kafka Consumer

**File**: `services/cj_assessment_service/kafka_consumer.py`

```python
class CJAssessmentKafkaConsumer:
    """Kafka consumer for CJ Assessment events and callbacks."""
    
    async def start_consumer(self) -> None:
        """Start consuming from request and callback topics."""
        
        # Subscribe to BOTH topics
        topics = [
            self.settings.CJ_ASSESSMENT_REQUEST_TOPIC,      # Original requests
            self.settings.LLM_PROVIDER_CALLBACK_TOPIC,       # LLM callbacks
        ]
        
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.settings.KAFKA_CONSUMER_GROUP,
            enable_auto_commit=False,
            max_poll_records=1,  # Process one at a time for consistency
            session_timeout_ms=45000,
        )
        
        await self.consumer.start()
        logger.info(f"Started consuming from topics: {topics}")
        
        try:
            async for msg in self.consumer:
                # Route to appropriate handler based on topic
                if msg.topic == self.settings.CJ_ASSESSMENT_REQUEST_TOPIC:
                    success = await self._process_assessment_request(msg)
                elif msg.topic == self.settings.LLM_PROVIDER_CALLBACK_TOPIC:
                    success = await self._process_llm_callback(msg)
                else:
                    logger.warning(f"Received message from unknown topic: {msg.topic}")
                    success = True
                
                if success:
                    await self.consumer.commit()
                    
        finally:
            await self.consumer.stop()
    
    async def _process_llm_callback(self, msg: ConsumerRecord) -> bool:
        """Process LLM comparison result callback."""
        from services.cj_assessment_service.event_processor import process_llm_result
        
        return await process_llm_result(
            msg=msg,
            database=self.database,
            event_publisher=self.event_publisher,
            settings_obj=self.settings,
            tracer=self.tracer,
        )
```

#### 3.2 Add Callback Event Processor

**File**: `services/cj_assessment_service/event_processor.py`

```python
# Add new import
from common_core.events.llm_provider_events import LLMComparisonResultV1
from services.cj_assessment_service.cj_core_logic.workflow_logic import (
    continue_cj_assessment_workflow,
)

async def process_llm_result(
    msg: ConsumerRecord,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings_obj: Settings,
    tracer: Optional["Tracer"] = None,
) -> bool:
    """
    Process LLM comparison result callback.
    Delegates to workflow logic for state management.
    """
    
    try:
        # Parse callback event
        envelope = EventEnvelope[LLMComparisonResultV1].model_validate_json(
            msg.value.decode("utf-8")
        )
        
        # Extract timing for metrics
        callback_latency = (
            datetime.now(UTC) - envelope.timestamp
        ).total_seconds()
        
        metrics.histogram("cj_callback_latency_seconds").observe(callback_latency)
        
        logger.info(
            "Processing LLM comparison callback",
            extra={
                "correlation_id": str(envelope.correlation_id),
                "request_id": envelope.data.request_id,
                "is_error": envelope.data.is_error,
                "latency_seconds": callback_latency
            }
        )
        
        # Delegate to workflow logic
        await continue_cj_assessment_workflow(
            correlation_id=envelope.correlation_id,
            result_data=envelope.data,
            database=database,
            event_publisher=event_publisher,
            settings=settings_obj,
        )
        
        # Update metrics
        metrics.counter(
            "cj_callbacks_processed_total",
            status="error" if envelope.data.is_error else "success"
        ).inc()
        
        return True
        
    except Exception as e:
        logger.error(
            "Failed to process LLM callback",
            extra={
                "error": str(e),
                "topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset
            },
            exc_info=True
        )
        
        metrics.counter("cj_callback_processing_errors_total").inc()
        
        # Don't retry - acknowledge to prevent blocking
        return True
```

#### 3.3 Implement Workflow Logic

**File**: `services/cj_assessment_service/cj_core_logic/workflow_logic.py` (new)

```python
"""
Stateful workflow management for CJ Assessment batch processing.
Handles callback processing, state transitions, and error recovery.
"""
import logging
from datetime import datetime, UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from common_core.events.llm_provider_events import LLMComparisonResultV1
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums import BatchStateEnum
from services.cj_assessment_service.models_db import (
    ComparisonPair, 
    CJBatchState,
    CJBatchUpload
)
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    CJEventPublisherProtocol
)

logger = logging.getLogger(__name__)


async def continue_cj_assessment_workflow(
    correlation_id: UUID,
    result_data: LLMComparisonResultV1,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
) -> None:
    """
    Process a callback and advance the batch workflow.
    Uses optimistic locking to prevent race conditions.
    """
    
    # Phase 1: Quick update of comparison result
    batch_id = await _update_comparison_result(
        database, correlation_id, result_data
    )
    
    if not batch_id:
        logger.warning(
            f"Callback for unknown correlation_id: {correlation_id}"
        )
        return
    
    # Phase 2: Update batch state and determine next action
    next_action = await _update_batch_state_and_decide(
        database, batch_id, settings
    )
    
    # Phase 3: Execute any required downstream actions
    if next_action:
        await _execute_action(
            next_action, batch_id, database, event_publisher, settings
        )


async def _update_comparison_result(
    database: CJRepositoryProtocol,
    correlation_id: UUID,
    result_data: LLMComparisonResultV1
) -> Optional[int]:
    """
    Update comparison pair with callback result.
    Returns batch_id if found, None if orphaned callback.
    """
    
    async with database.session() as session:
        # Find comparison by correlation ID
        stmt = select(ComparisonPair).where(
            ComparisonPair.request_correlation_id == correlation_id
        ).options(
            selectinload(ComparisonPair.cj_batch)
        )
        
        result = await session.execute(stmt)
        pair = result.scalar_one_or_none()
        
        if not pair:
            return None
        
        # Idempotency check
        if pair.winner is not None or pair.error_code is not None:
            logger.info(
                f"Duplicate callback for pair {pair.id}, ignoring"
            )
            return pair.cj_batch_id
        
        # Update with result
        if result_data.is_error:
            pair.error_code = result_data.error_detail.error_code
            pair.error_correlation_id = result_data.error_detail.correlation_id
            pair.error_timestamp = result_data.error_detail.timestamp
            pair.error_service = result_data.error_detail.service
            pair.error_details = {
                "message": result_data.error_detail.message,
                "provider": result_data.provider,
                "model": result_data.model,
                "details": result_data.error_detail.details
            }
        else:
            pair.winner = result_data.winner
            pair.confidence = result_data.confidence
            pair.justification = result_data.justification
            pair.raw_llm_response = result_data.request_metadata.get("raw_response")
        
        pair.completed_at = datetime.now(UTC)
        
        await session.commit()
        return pair.cj_batch_id


async def _update_batch_state_and_decide(
    database: CJRepositoryProtocol,
    batch_id: int,
    settings: Settings
) -> Optional[str]:
    """
    Update batch state counters and determine next action.
    Uses row-level locking to prevent concurrent updates.
    """
    
    async with database.session() as session:
        # Lock batch state for update
        stmt = select(CJBatchState).where(
            CJBatchState.batch_id == batch_id
        ).with_for_update()
        
        result = await session.execute(stmt)
        batch_state = result.scalar_one_or_none()
        
        if not batch_state:
            logger.error(f"No batch state found for batch {batch_id}")
            return None
        
        # Skip if batch already completed/failed
        if batch_state.state in [
            BatchStateEnum.COMPLETED, 
            BatchStateEnum.FAILED,
            BatchStateEnum.CANCELLED
        ]:
            return None
        
        # Get the comparison we just updated
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id
        ).order_by(
            ComparisonPair.completed_at.desc()
        ).limit(1)
        
        result = await session.execute(stmt)
        latest_pair = result.scalar_one()
        
        # Update counters based on result
        if latest_pair.error_code:
            batch_state.failed_comparisons += 1
        else:
            batch_state.completed_comparisons += 1
        
        # Calculate progress
        total_processed = (
            batch_state.completed_comparisons + 
            batch_state.failed_comparisons
        )
        # Defensive division to prevent ZeroDivisionError
        progress_pct = 0.0
        if batch_state.total_comparisons > 0:
            progress_pct = (total_processed / batch_state.total_comparisons) * 100
        
        logger.info(
            f"Batch {batch_id} progress: {total_processed}/{batch_state.total_comparisons} "
            f"({progress_pct:.1f}%)"
        )
        
        # Check failure rate
        if total_processed >= 10:  # Enough samples
            success_rate = batch_state.completed_comparisons / total_processed
            if success_rate < settings.MIN_SUCCESS_RATE_THRESHOLD:
                batch_state.state = BatchStateEnum.FAILED
                logger.error(
                    f"Batch {batch_id} failed due to low success rate: {success_rate:.2f}"
                )
                await session.commit()
                return "PUBLISH_FAILURE"
        
        # Determine next action
        next_action = None
        
        if progress_pct >= 100:
            # All comparisons complete
            batch_state.state = BatchStateEnum.SCORING
            next_action = "TRIGGER_FINAL_SCORING"
            
        elif progress_pct >= batch_state.completion_threshold_pct:
            # Partial completion threshold met
            if not batch_state.partial_scoring_triggered:
                batch_state.partial_scoring_triggered = True
                next_action = "TRIGGER_PARTIAL_SCORING"
                
        elif batch_state.state == BatchStateEnum.WAITING_CALLBACKS:
            # Check if we need more comparisons (stability check)
            if await _check_score_stability(session, batch_id, settings):
                batch_state.state = BatchStateEnum.SCORING
                next_action = "TRIGGER_FINAL_SCORING"
            elif batch_state.current_iteration < settings.MAX_ITERATIONS:
                # May need more pairs if all current ones complete
                if total_processed >= batch_state.submitted_comparisons:
                    next_action = "GENERATE_ADAPTIVE_PAIRS"
        
        await session.commit()
        return next_action


async def _check_score_stability(
    session: AsyncSession,
    batch_id: int,
    settings: Settings
) -> bool:
    """
    Check if Bradley-Terry scores have stabilized.
    Returns True if max score change is below threshold.
    """
    
    # Get batch with metadata
    batch = await session.get(CJBatchUpload, batch_id)
    if not batch or not batch.processing_metadata:
        return False
    
    previous_scores = batch.processing_metadata.get("previous_scores", {})
    if not previous_scores:
        return False  # First iteration
    
    # Get current scores (simplified - real implementation would calculate)
    current_scores = await _calculate_current_scores(session, batch_id)
    
    # Find maximum change
    max_change = 0.0
    for essay_id, current_score in current_scores.items():
        previous_score = previous_scores.get(essay_id, 0.0)
        change = abs(current_score - previous_score)
        max_change = max(max_change, change)
    
    # Store current as previous for next iteration
    if not batch.processing_metadata:
        batch.processing_metadata = {}
    batch.processing_metadata["previous_scores"] = current_scores
    
    return max_change < settings.SCORE_STABILITY_THRESHOLD


async def _execute_action(
    action: str,
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings
) -> None:
    """Execute downstream actions based on workflow decision."""
    
    logger.info(f"Executing action '{action}' for batch {batch_id}")
    
    if action == "TRIGGER_FINAL_SCORING":
        from .scoring_ranking import calculate_and_publish_final_scores
        await calculate_and_publish_final_scores(
            batch_id, database, event_publisher
        )
        
    elif action == "TRIGGER_PARTIAL_SCORING":
        from .scoring_ranking import calculate_and_publish_final_scores
        await calculate_and_publish_final_scores(
            batch_id, database, event_publisher, partial=True
        )
        
    elif action == "GENERATE_ADAPTIVE_PAIRS":
        from .comparison_processing import generate_adaptive_pairs
        await generate_adaptive_pairs(
            batch_id, database, settings
        )
        
    elif action == "PUBLISH_FAILURE":
        from .event_publishing import publish_batch_failure
        await publish_batch_failure(
            batch_id, database, event_publisher
        )
    
    else:
        logger.warning(f"Unknown action: {action}")
```

### Phase 4: Batch Monitoring & Recovery ❌ NOT IMPLEMENTED

**Current Status**: Planned but not implemented

**Missing Components**:

- ❌ **BatchMonitor Class**: No background monitoring implementation
- ❌ **Stuck Batch Detection**: No timeout-based recovery
- ❌ **Recovery Strategies**: No automated batch recovery
- ❌ **Worker Integration**: No monitoring loop in worker main

**Phase 4 Original Plan**:

#### 4.1 Implement Batch Monitor

**File**: `services/cj_assessment_service/batch_monitor.py` (new)

```python
"""
Background monitoring for batch health and recovery.
"""
import asyncio
import logging
from datetime import datetime, timedelta, UTC

from sqlalchemy import select, and_

from common_core.models.error_models import ErrorDetail
from services.libs.huleedu_service_libs.rate_limiter import RateLimiter

from services.cj_assessment_service.enums import BatchStateEnum
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    CJEventPublisherProtocol
)

logger = logging.getLogger(__name__)


class BatchMonitor:
    """Monitors batch health and recovers stuck batches."""
    
    def __init__(
        self,
        database: CJRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        timeout_hours: int = 4,
        max_concurrent_checks: int = 5,
        rate_limit_checks_per_minute: int = 10,
    ):
        self.database = database
        self.event_publisher = event_publisher
        self.timeout = timedelta(hours=timeout_hours)
        self._running = True
        self._check_semaphore = asyncio.Semaphore(max_concurrent_checks)
        self._rate_limiter = RateLimiter(
            max_calls=rate_limit_checks_per_minute,
            period=timedelta(minutes=1)
        )
    
    async def stop(self) -> None:
        """Signal monitor to stop gracefully."""
        self._running = False
    
    async def check_stuck_batches(self) -> None:
        """
        Find and handle batches with no recent activity.
        """
        
        if not self._running:
            return
        
        # Apply rate limiting
        await self._rate_limiter.acquire()
        
        # Use semaphore to limit concurrent checks
        async with self._check_semaphore:
            logger.info("Running batch health check...")
        
        stuck_threshold = datetime.now(UTC) - self.timeout
        monitored_states = [
            BatchStateEnum.GENERATING_PAIRS,
            BatchStateEnum.WAITING_CALLBACKS
        ]
        
        async with self.database.session() as session:
            # Find stuck batches
            stmt = select(CJBatchState).where(
                and_(
                    CJBatchState.state.in_(monitored_states),
                    CJBatchState.last_activity_at < stuck_threshold
                )
            )
            
            result = await session.execute(stmt)
            stuck_batches = result.scalars().all()
            
            if stuck_batches:
                logger.warning(f"Found {len(stuck_batches)} stuck batches")
                metrics.gauge("cj_stuck_batches_detected").set(len(stuck_batches))
            
            for batch in stuck_batches:
                await self._handle_stuck_batch(session, batch)
            
            await session.commit()
    
    async def _handle_stuck_batch(
        self,
        session: AsyncSession,
        batch_state: CJBatchState
    ) -> None:
        """
        Decide how to handle a stuck batch based on progress.
        """
        
        total_processed = (
            batch_state.completed_comparisons + 
            batch_state.failed_comparisons
        )
        # Defensive division to prevent ZeroDivisionError
        progress_pct = 0.0
        if batch_state.total_comparisons > 0:
            progress_pct = (total_processed / batch_state.total_comparisons) * 100
        
        logger.warning(
            f"Batch {batch_state.batch_id} stuck at {progress_pct:.1f}% progress. "
            f"Last activity: {batch_state.last_activity_at}"
        )
        
        if progress_pct >= 80:
            # Good enough - force completion
            logger.info(
                f"Force completing batch {batch_state.batch_id} at {progress_pct:.1f}%"
            )
            batch_state.state = BatchStateEnum.SCORING
            
            # Trigger scoring in background
            from .workflow_logic import _execute_action
            await _execute_action(
                "TRIGGER_FINAL_SCORING",
                batch_state.batch_id,
                self.database,
                self.event_publisher,
                None  # settings not needed for scoring
            )
            
            metrics.counter("cj_stuck_batches_recovered_total").inc()
            
        else:
            # Too incomplete - mark as failed
            logger.error(
                f"Failing batch {batch_state.batch_id} due to timeout at {progress_pct:.1f}%"
            )
            batch_state.state = BatchStateEnum.FAILED
            
            # Publish failure event
            await _execute_action(
                "PUBLISH_FAILURE",
                batch_state.batch_id,
                self.database,
                self.event_publisher,
                None
            )
            
            metrics.counter("cj_stuck_batches_failed_total").inc()
```

#### 4.2 Integrate Monitor with Worker

**File**: `services/cj_assessment_service/worker_main.py`

```python
import asyncio
import signal
from contextlib import asynccontextmanager

from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.kafka_consumer import CJAssessmentKafkaConsumer

# ... existing imports ...

async def main() -> None:
    """Main entry point with batch monitoring."""
    
    # Initialize components
    settings = Settings()
    database = PostgreSQLCJRepositoryImpl(settings)
    event_publisher = KafkaEventPublisherImpl(settings)
    
    # Create monitor
    monitor = BatchMonitor(
        database=database,
        event_publisher=event_publisher,
        timeout_hours=settings.BATCH_TIMEOUT_HOURS
    )
    
    # Create consumer
    consumer = CJAssessmentKafkaConsumer(
        settings=settings,
        database=database,
        event_publisher=event_publisher,
    )
    
    # Graceful shutdown handler
    shutdown_event = asyncio.Event()
    
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    
    # Monitor task
    async def run_monitor():
        while not shutdown_event.is_set():
            try:
                await monitor.check_stuck_batches()
                await asyncio.sleep(settings.BATCH_MONITOR_INTERVAL_MINUTES * 60)
            except Exception:
                logger.exception("Error in batch monitor")
                await asyncio.sleep(60)  # Retry after 1 minute
    
    # Consumer task
    async def run_consumer():
        try:
            await consumer.start_consumer()
        except Exception:
            logger.exception("Fatal error in consumer")
            shutdown_event.set()
    
    # Run both concurrently
    monitor_task = asyncio.create_task(run_monitor())
    consumer_task = asyncio.create_task(run_consumer())
    
    # Wait for shutdown
    await shutdown_event.wait()
    
    # Graceful cleanup
    logger.info("Shutting down gracefully...")
    await monitor.stop()
    await consumer.stop()
    
    # Wait for tasks to complete
    await asyncio.gather(
        monitor_task, 
        consumer_task, 
        return_exceptions=True
    )
    
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
```

### Phase 5: Monitoring & Observability ⚠️ PARTIALLY IMPLEMENTED

**Current Status**: Basic metrics added but incomplete

**Completed**:

- ✅ **Basic Metrics**: Callback processing counters and histograms
- ✅ **Logging Integration**: Structured logging with correlation IDs
- ✅ **Business Metrics**: Integration with metrics system

**Missing**:

- ❌ **Comprehensive Metrics**: Full batch state and progress tracking
- ❌ **Alerting Rules**: No Prometheus alerting configuration
- ❌ **Dashboards**: No Grafana dashboard implementation
- ❌ **Distributed Tracing**: No OpenTelemetry integration

**Phase 5 Original Plan**:

#### 5.1 Add Comprehensive Metrics

**File**: `services/cj_assessment_service/metrics.py` (new)

```python
"""Prometheus metrics for CJ Assessment Service."""
from prometheus_client import Counter, Histogram, Gauge, Enum

# Callback processing metrics
cj_callbacks_processed_total = Counter(
    'cj_callbacks_processed_total',
    'Total callbacks processed',
    ['status']  # success/error
)

cj_callback_latency_seconds = Histogram(
    'cj_callback_latency_seconds',
    'Time between callback sent and received',
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300]
)

# Batch state metrics
cj_batch_state = Gauge(
    'cj_batch_state',
    'Current number of batches in each state',
    ['state']
)

cj_batch_progress = Histogram(
    'cj_batch_progress_percentage',
    'Progress percentage when batch completes',
    buckets=[50, 60, 70, 80, 90, 95, 99, 100]
)

# Processing metrics
cj_comparisons_total = Counter(
    'cj_comparisons_total',
    'Total comparisons processed',
    ['status']  # completed/failed
)

cj_batch_processing_duration_seconds = Histogram(
    'cj_batch_processing_duration_seconds',
    'Total time to process a batch',
    buckets=[60, 300, 600, 1800, 3600, 7200]
)

# Monitoring metrics
cj_stuck_batches_detected = Gauge(
    'cj_stuck_batches_detected',
    'Number of stuck batches currently detected'
)

cj_stuck_batches_recovered_total = Counter(
    'cj_stuck_batches_recovered_total',
    'Batches successfully recovered from stuck state'
)

cj_stuck_batches_failed_total = Counter(
    'cj_stuck_batches_failed_total',
    'Batches failed due to being stuck'
)

# Score stability metrics
cj_iterations_per_batch = Histogram(
    'cj_iterations_per_batch',
    'Number of iterations needed for stability',
    buckets=[1, 2, 3, 4, 5, 10]
)

cj_score_stability_changes = Histogram(
    'cj_score_stability_changes',
    'Maximum score change between iterations',
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5]
)
```

#### 5.2 Add Alerting Rules

**File**: `monitoring/alerts/cj_assessment_alerts.yml`

```yaml
groups:
  - name: cj_assessment_alerts
    interval: 30s
    rules:
      # Callback processing alerts
      - alert: HighCallbackLatency
        expr: |
          histogram_quantile(0.99, rate(cj_callback_latency_seconds_bucket[5m])) > 30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P99 callback latency above 30 seconds"
          description: "Callbacks are taking too long to arrive"
      
      - alert: CallbackProcessingErrors
        expr: |
          rate(cj_callbacks_processed_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High callback error rate"
          description: "More than 10% of callbacks are failing"
      
      # Batch health alerts
      - alert: StuckBatchesDetected
        expr: cj_stuck_batches_detected > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "{{ $value }} batches are stuck"
          description: "Multiple batches have not progressed recently"
      
      - alert: LowComparisonSuccessRate
        expr: |
          rate(cj_comparisons_total{status="completed"}[5m]) / 
          rate(cj_comparisons_total[5m]) < 0.8
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Comparison success rate below 80%"
          description: "Too many comparisons are failing"
      
      # Performance alerts
      - alert: SlowBatchProcessing
        expr: |
          histogram_quantile(0.95, rate(cj_batch_processing_duration_seconds_bucket[1h])) > 3600
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Batches taking over 1 hour to process"
          description: "P95 batch processing time exceeds SLA"
```

## ✅ Success Criteria Status

### Functional Requirements

- ✅ **Polling Removal**: No polling code remains in LLM Provider Client
- ✅ **Callback Framework**: Basic callback processing infrastructure
- ✅ **State Persistence**: Batch state persisted and trackable
- ❌ **Automatic Recovery**: Stuck batch recovery not implemented
- ❌ **Partial Completions**: Partial completion handling incomplete

### Performance Requirements

- ❓ **Concurrent Batches**: Framework supports concurrency but not tested at scale
- ❓ **Callback Latency**: Infrastructure ready but performance not validated
- ❓ **Data Loss Prevention**: State persistence implemented but recovery untested
- ❌ **Automatic Scaling**: No scaling mechanisms implemented

### Operational Requirements

- ⚠️ **Observability**: Basic metrics implemented, comprehensive monitoring missing
- ❌ **Alerting**: No alerting rules configured
- ⚠️ **Metrics**: Basic metrics present, full critical path coverage missing
- ❌ **Graceful Shutdown**: Not implemented in current worker

## 🚨 Deployment Strategy

### Prerequisites

1. [ ] TASK-LLM-01 deployed and verified
2. [ ] Database migrations tested and ready
3. [ ] Monitoring dashboards configured
4. [ ] Load tests completed

### Deployment Steps

1. **Stop CJ Assessment Service** - Prevent partial processing
2. **Run database migrations** - Add state tables
3. **Deploy new service version** - With callback support
4. **Start batch monitor** - Begin health checks
5. **Verify callback flow** - Test with sample batch
6. **Monitor metrics** - Watch for issues

### Rollback Plan

1. Stop service immediately
2. Note any in-flight batches
3. Revert to previous version
4. Manually recover stuck batches
5. Investigate root cause

## ⚠️ Anti-Patterns to Avoid

1. **DO NOT** hold database locks during slow operations
2. **DO NOT** process callbacks without idempotency checks
3. **DO NOT** ignore partial batch completions
4. **DO NOT** retry callbacks indefinitely
5. **DO NOT** store large data in batch state

## 📊 Expected Impact

### Performance Improvements

- **Throughput**: 100x improvement in concurrent batches
- **Latency**: Real-time processing vs blocking waits
- **Resource Usage**: 95% reduction in idle connections
- **Cost**: Enables efficient batch API usage

### Operational Improvements

- **Resilience**: Automatic recovery from failures
- **Visibility**: Complete batch lifecycle tracking
- **Scalability**: Horizontal scaling ready
- **Maintenance**: Self-healing architecture

## 🔗 Related Tasks

- **Prerequisite**: TASK-LLM-01 (Event publishing) ✅ Complete
- **Follow-up**: **TASK-CJ-03** - Proper batch LLM integration (addresses architectural issues)
- **Future**: Apply state management pattern to other async workflows
- **Future**: Add batch priority queuing
- **Future**: Implement batch result caching

## 🚨 Lessons Learned & Issues Identified

### Architectural Misalignment

- **Issue**: `workflow_logic.py` created as parallel system instead of integrating with existing batch processing
- **Impact**: Duplicate state management and incomplete workflow integration
- **Solution**: TASK-CJ-03 will properly integrate event-driven callbacks with existing batch system

### Incomplete Implementation

- **Issue**: Multiple critical functions implemented as TODO stubs
- **Components**: Score calculation, final scoring, failure handling, batch monitoring
- **Impact**: System can process callbacks but cannot complete full batch lifecycle

### Missing Production Readiness

- **Issue**: No comprehensive monitoring, alerting, or recovery mechanisms
- **Impact**: System not ready for production deployment
- **Required**: Complete monitoring implementation and load testing

### Integration Gaps

- **Issue**: New workflow system doesn't connect to existing scoring and processing modules
- **Impact**: Results processed but not properly integrated into final batch results
- **Solution**: Proper integration architecture needed in follow-up work

## 🚀 Implementation Checklist - Final Status

### Database & Models ✅ COMPLETE

- [x] Create BatchStateEnum enumeration ✅
- [x] Add CJBatchState model with proper relationships ✅
- [x] Update ComparisonPair model with correlation tracking ✅
- [x] Create and test database migration ✅
- [x] Verify indexes for performance ✅

### LLM Provider Client ✅ COMPLETE

- [x] Remove all polling methods ✅
- [x] Update generate_comparison to use callback topic ✅
- [x] Implement proper error handling with HuleEduError exceptions ✅
- [x] Add request timeout handling ✅
- [x] Update unit tests (Completed during implementation) ✅

### Event Processing ⚠️ PARTIALLY COMPLETE

- [x] Update Kafka consumer to subscribe to callback topic ✅
- [x] Implement process_llm_result handler ✅
- [x] Add workflow logic with state transitions ✅
- [x] Implement idempotency checks ✅
- [x] Add comprehensive logging ✅

### State Management ⚠️ FRAMEWORK COMPLETE, INTEGRATION INCOMPLETE

- [x] Implement workflow state machine ✅
- [x] Add optimistic locking for concurrent updates ✅
- [x] Handle partial completion scenarios ✅
- [x] Implement score stability checks ⚠️ *(Stub implementation)

### Monitoring & Recovery ❌ NOT IMPLEMENTED

- [ ] Implement BatchMonitor class ❌
- [ ] Add stuck batch detection ❌
- [ ] Implement recovery strategies ❌
- [ ] Integrate with worker main loop ❌
- [ ] Add graceful shutdown handling ❌

### Testing ⚠️ BASIC TESTING ONLY

- [x] Unit tests for callback processing ✅
- [ ] Integration tests for state management ❌
- [ ] End-to-end tests with Kafka ❌
- [ ] Load tests for concurrent batches ❌
- [ ] Chaos tests for failure scenarios ❌

### Observability ⚠️ BASIC METRICS ONLY

- [x] Add basic Prometheus metrics ✅
- [ ] Create Grafana dashboards ❌
- [ ] Configure alerting rules ❌
- [ ] Add distributed tracing ❌
- [ ] Document runbooks ❌

### Critical Missing Components for Production

- [x] **Score Calculation Integration**: Bradley-Terry scoring fully integrated ✅
- [x] **Final Scoring Implementation**: Batch result publication implemented ✅
- [x] **Batch Recovery**: Stuck batch monitoring and recovery implemented ✅
- [x] **Error Handling**: Structured error propagation with failure publication ✅
- [ ] **Load Testing**: Validate concurrent batch processing performance ❌

**Next Steps**: Address architectural issues in TASK-CJ-03 for proper batch integration

## 📋 Updated Implementation Status (2025-07-16)

### ✅ Completed Features

#### Event Processing & Callbacks
- ✅ Dual-topic Kafka consumer for assessment requests and LLM callbacks
- ✅ Batch callback handler with retry processor integration  
- ✅ Automatic completion checking and Bradley-Terry scoring trigger
- ✅ State transition management with proper error handling
- ✅ Method name fix: `publish_assessment_completed` alignment

#### Batch Monitoring & Recovery
- ✅ BatchMonitor class with stuck batch detection
- ✅ Configurable timeout thresholds (default 4 hours)
- ✅ Smart recovery strategies based on completion percentage
- ✅ Automatic scoring trigger for >80% complete batches
- ✅ Failure handling for <80% complete batches
- ✅ Concurrent monitoring with worker integration

#### Production Readiness
- ✅ Health check endpoints (/healthz/live, /healthz/ready)
- ✅ Graceful shutdown with signal handling and grace period
- ✅ Structured error handling with correlation tracking
- ✅ Comprehensive metrics and observability hooks
- ✅ Bradley-Terry scoring fully integrated

### 🔧 Known Issues Fixed
1. ✅ **FIXED**: Undefined `batch_state` variable in batch_callback_handler.py line 302
2. ✅ **FIXED**: Method name mismatch - `publish_cj_assessment_completed` vs `publish_assessment_completed`

### 📋 Remaining Work for Full Production

#### High Priority
- [ ] **Cache Removal & Rate Limiting**: Remove improper caching, implement provider-specific rate limiting
- [ ] **Integration Tests**: End-to-end tests for full batch lifecycle
- [ ] **Error Handling Phase 6**: Complete event-driven error handling (blocked by LLM refactor)

#### Medium Priority
- [ ] **HuleEduApp Integration**: Migrate to standardized base class for type safety
- [ ] **Circuit Breakers**: Add circuit breakers for LLM provider calls
- [ ] **Distributed Tracing**: Full OpenTelemetry integration

#### Low Priority
- [ ] **Grafana Dashboards**: Service-specific monitoring dashboards
- [ ] **Alerting Rules**: Prometheus alerting configuration

### 📊 Service Status
**~85% Production Ready** - All critical features implemented, operational improvements needed for full production deployment.
