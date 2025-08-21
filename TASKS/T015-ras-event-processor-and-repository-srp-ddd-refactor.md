# T015 — RAS Event Processor and Repository SRP/DDD Refactor

## Context

The Result Aggregator Service has two large modules that violate SRP:
- `services/result_aggregator_service/implementations/event_processor_impl.py` (~761 LoC)
- `services/result_aggregator_service/implementations/batch_repository_postgres_impl.py` (~761 LoC)

Following our established patterns from Essay Lifecycle Service refactoring, we will split these into focused modules while maintaining flat implementation structure and consistent DI patterns.

## Goals

- Enforce SRP within RAS event processing and persistence layers
- Preserve public interfaces: `EventProcessorProtocol` and `BatchRepositoryProtocol`
- Follow established service patterns (flat implementations directory, no nested structures)
- Maintain separation between processing different event types
- No backwards compatibility layers (pure dev environment)
- Target ~200-400 LoC per module

## Non-Goals

- No nested directory structures under implementations
- No backward compatibility layers or legacy shims
- No changes to event contracts or Kafka topics
- No modification of the dual-event pattern
- No changes to protocol interfaces

## End-State Architecture

### Event Processor Implementation (Flat Structure)

```
services/result_aggregator_service/implementations/
├── event_processor_impl.py              # Facade (~150 LoC)
├── batch_lifecycle_handler.py           # Batch registration, phases, completion (~250 LoC)
├── spellcheck_event_handler.py          # Thin & rich spellcheck events (~200 LoC)
├── assessment_event_handler.py          # CJ assessment events (~200 LoC)
├── batch_completion_calculator.py       # Completion checks & statistics (~200 LoC)
```

### Repository Implementation (Flat Structure)

```
services/result_aggregator_service/implementations/
├── batch_repository_postgres_impl.py    # Facade (~200 LoC)
├── batch_repository_queries.py          # CRUD operations (~400 LoC)
├── essay_result_updater.py              # Essay update operations (~250 LoC)
├── batch_statistics_calculator.py       # Statistics & aggregations (~200 LoC)
├── batch_repository_mappers.py          # DB↔domain mapping (~100 LoC)
```

## Implementation Phases

### Phase 1: EventProcessor - Extract Batch Lifecycle Handler

**Objective**: Extract batch lifecycle operations from EventProcessorImpl

**New Module: `batch_lifecycle_handler.py`**
```python
"""Handles batch lifecycle events for Result Aggregator Service."""

from typing import TYPE_CHECKING
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import BatchEssaysRegistered, EventEnvelope
    from common_core.events.batch_coordination_events import (
        BatchPipelineCompletedV1,
        ELSBatchPhaseOutcomeV1,
    )
    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        EventPublisherProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.batch_lifecycle")

class BatchLifecycleHandler:
    """Handles batch registration, phase outcomes, and pipeline completion."""
    
    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        event_publisher: "EventPublisherProtocol",
    ):
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.event_publisher = event_publisher
        
    async def process_batch_registered(
        self,
        envelope: "EventEnvelope[BatchEssaysRegistered]",
        data: "BatchEssaysRegistered",
    ) -> None:
        """Process batch registration event."""
        # Extract logic from event_processor_impl.py lines 60-143
        
    async def process_batch_phase_outcome(
        self,
        envelope: "EventEnvelope[ELSBatchPhaseOutcomeV1]",
        data: "ELSBatchPhaseOutcomeV1",
    ) -> None:
        """Process batch phase outcome event."""
        # Extract logic from event_processor_impl.py lines 188-311
        
    async def process_pipeline_completed(
        self,
        event: "BatchPipelineCompletedV1",
    ) -> None:
        """Process pipeline completion for final result aggregation."""
        # Extract logic from event_processor_impl.py lines 601-646
```

**Validation Steps**:
1. Run existing batch lifecycle tests
2. Verify batch registration creates records
3. Verify phase outcomes update status correctly
4. Check pipeline completion triggers final aggregation
5. Run type checking

### Phase 2: EventProcessor - Extract Spellcheck Event Handler

**Objective**: Extract spellcheck event handling (both thin and rich events)

**New Module: `spellcheck_event_handler.py`**
```python
"""Handles spellcheck events for Result Aggregator Service."""

from typing import TYPE_CHECKING, Optional
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import EventEnvelope, SpellcheckResultDataV1, SpellcheckResultV1
    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.spellcheck_handler")

class SpellcheckEventHandler:
    """Handles both thin and rich spellcheck events following dual-event pattern."""
    
    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
    ):
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        
    async def process_spellcheck_completed(
        self,
        envelope: "EventEnvelope[SpellcheckResultDataV1]",
        data: "SpellcheckResultDataV1",
    ) -> None:
        """Process thin spellcheck completion event."""
        # Extract logic from event_processor_impl.py lines 313-404
        
    async def process_spellcheck_result(
        self,
        envelope: "EventEnvelope[SpellcheckResultV1]",
        data: "SpellcheckResultV1",
    ) -> None:
        """Process rich spellcheck result event with business metrics."""
        # Extract logic from event_processor_impl.py lines 406-500
```

**Validation Steps**:
1. Run spellcheck event tests
2. Verify thin events update status
3. Verify rich events capture metrics
4. Check dual-event pattern preserved
5. Run type checking

### Phase 3: EventProcessor - Extract Assessment Event Handler

**Objective**: Extract CJ assessment and essay slot assignment handling

**New Module: `assessment_event_handler.py`**
```python
"""Handles assessment events for Result Aggregator Service."""

from typing import TYPE_CHECKING, Any
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import EventEnvelope
    from common_core.events.assessment_result_events import AssessmentResultV1
    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.assessment_handler")

class AssessmentEventHandler:
    """Handles CJ assessment results and essay file mapping."""
    
    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
    ):
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        
    async def process_essay_slot_assigned(
        self,
        envelope: "EventEnvelope[Any]",
        data: Any,  # EssaySlotAssignedV1
    ) -> None:
        """Process essay slot assignment for file traceability."""
        # Extract logic from event_processor_impl.py lines 145-186
        
    async def process_assessment_result(
        self,
        envelope: "EventEnvelope[AssessmentResultV1]",
        data: "AssessmentResultV1",
    ) -> None:
        """Process rich CJ assessment result with business data."""
        # Extract logic from event_processor_impl.py lines 502-599
```

**Validation Steps**:
1. Run assessment event tests
2. Verify CJ results properly stored
3. Verify file traceability maintained
4. Check ranking/scoring captured
5. Run type checking

### Phase 4: EventProcessor - Extract Batch Completion Calculator

**Objective**: Extract batch completion checking and statistics calculation

**New Module: `batch_completion_calculator.py`**
```python
"""Calculates batch completion and statistics for Result Aggregator Service."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from common_core.status_enums import BatchStatus
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events.result_events import PhaseResultSummary
    from services.result_aggregator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.completion_calculator")

class BatchCompletionCalculator:
    """Calculates batch completion status and phase statistics."""
    
    def __init__(self, batch_repository: "BatchRepositoryProtocol"):
        self.batch_repository = batch_repository
        
    async def check_batch_completion(self, batch_id: str) -> bool:
        """Check if all phases are complete for a batch."""
        # Extract logic from event_processor_impl.py lines 648-672
        
    async def calculate_phase_results(self, batch_id: str) -> List["PhaseResultSummary"]:
        """Calculate phase results for completed batch."""
        # Extract logic from event_processor_impl.py lines 674-738
        
    def determine_overall_status(
        self, phase_results: List["PhaseResultSummary"]
    ) -> BatchStatus:
        """Determine overall batch status from phase results."""
        # Extract logic from event_processor_impl.py lines 740-748
        
    async def calculate_duration(self, batch_id: str) -> Optional[float]:
        """Calculate processing duration for a batch."""
        # Extract logic from event_processor_impl.py lines 750-760
```

**Validation Steps**:
1. Run completion calculation tests
2. Verify phase statistics accurate
3. Verify overall status determination
4. Check duration calculations
5. Run type checking

### Phase 5: EventProcessor - Update Facade Implementation

**Objective**: Create thin facade that delegates to specialized handlers

**Update: `event_processor_impl.py`**
```python
"""Event processor facade for Result Aggregator Service."""

from typing import TYPE_CHECKING
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.implementations.assessment_event_handler import (
    AssessmentEventHandler,
)
from services.result_aggregator_service.implementations.batch_completion_calculator import (
    BatchCompletionCalculator,
)
from services.result_aggregator_service.implementations.batch_lifecycle_handler import (
    BatchLifecycleHandler,
)
from services.result_aggregator_service.implementations.spellcheck_event_handler import (
    SpellcheckEventHandler,
)

if TYPE_CHECKING:
    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        EventProcessorProtocol,
        EventPublisherProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.event_processor")

class EventProcessorImpl(EventProcessorProtocol):
    """Facade for event processing that delegates to specialized handlers."""
    
    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
        event_publisher: "EventPublisherProtocol",
    ):
        """Initialize with dependencies and create handlers."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher
        
        # Initialize specialized handlers
        self.batch_lifecycle = BatchLifecycleHandler(
            batch_repository, state_store, event_publisher
        )
        self.spellcheck_handler = SpellcheckEventHandler(
            batch_repository, state_store, cache_manager
        )
        self.assessment_handler = AssessmentEventHandler(
            batch_repository, state_store, cache_manager
        )
        self.completion_calculator = BatchCompletionCalculator(batch_repository)
        
    # Delegate all protocol methods to appropriate handlers
```

**Validation Steps**:
1. Run full event processor test suite
2. Verify all events properly delegated
3. Check protocol compliance
4. Run integration tests
5. Run type checking

### Phase 6: Repository - Extract Query Operations

**Objective**: Extract database query operations

**New Module: `batch_repository_queries.py`**
```python
"""Database query operations for Result Aggregator Service."""

import time
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.result_aggregator_service.models_db import BatchResult, EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.queries")

class BatchRepositoryQueries:
    """Handles database query operations for batches and essays."""
    
    def __init__(self, session_factory: "async_sessionmaker"):
        self.session_factory = session_factory
        
    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch result by ID."""
        # Extract logic from batch_repository_postgres_impl.py lines 105-130
        
    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[dict] = None,
    ) -> BatchResult:
        """Create a new batch result."""
        # Extract logic from batch_repository_postgres_impl.py lines 155-176
        
    async def get_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BatchResult]:
        """Get batches for a user."""
        # Extract logic from batch_repository_postgres_impl.py lines 132-153
        
    async def get_batch_essays(self, batch_id: str) -> List[EssayResult]:
        """Get all essays for a batch."""
        # Extract logic from batch_repository_postgres_impl.py lines 651-703
```

**Validation Steps**:
1. Run query operation tests
2. Verify CRUD operations work
3. Check transaction handling
4. Verify selectinload working
5. Run type checking

### Phase 7: Repository - Extract Essay Result Updater

**Objective**: Extract essay result update operations

**New Module: `essay_result_updater.py`**
```python
"""Essay result update operations for Result Aggregator Service."""

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from services.result_aggregator_service.models_db import EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.essay_updater")

class EssayResultUpdater:
    """Handles essay result update operations."""
    
    def __init__(self, session_factory: "async_sessionmaker"):
        self.session_factory = session_factory
        
    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay spellcheck results."""
        # Extract logic from batch_repository_postgres_impl.py lines 220-281
        
    async def update_essay_spellcheck_result_with_metrics(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
        l2_corrections: Optional[int] = None,
        spell_corrections: Optional[int] = None,
        word_count: Optional[int] = None,
        correction_density: Optional[float] = None,
        processing_duration_ms: Optional[int] = None,
    ) -> None:
        """Update essay with detailed spellcheck metrics."""
        # Extract logic from batch_repository_postgres_impl.py lines 283-384
        
    async def update_essay_cj_assessment_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        rank: Optional[int] = None,
        score: Optional[float] = None,
        comparison_count: Optional[int] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay CJ assessment results."""
        # Extract logic from batch_repository_postgres_impl.py lines 386-451
```

**Validation Steps**:
1. Run essay update tests
2. Verify spellcheck updates work
3. Verify metrics properly stored
4. Verify CJ updates work
5. Run type checking

### Phase 8: Repository - Extract Statistics Calculator

**Objective**: Extract statistics and aggregation operations

**New Module: `batch_statistics_calculator.py`**
```python
"""Batch statistics calculation for Result Aggregator Service."""

from typing import TYPE_CHECKING, Dict, Any
from datetime import datetime, UTC

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, func

from services.result_aggregator_service.models_db import BatchResult, EssayResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("result_aggregator.statistics")

class BatchStatisticsCalculator:
    """Calculates batch statistics and aggregations."""
    
    def __init__(self, session_factory: "async_sessionmaker"):
        self.session_factory = session_factory
        
    async def calculate_phase_statistics(
        self,
        batch_id: str,
        phase: str,
    ) -> Dict[str, Any]:
        """Calculate statistics for a specific phase."""
        # Extract aggregation logic from various methods
        
    async def calculate_batch_completion_stats(
        self,
        batch_id: str,
    ) -> Dict[str, Any]:
        """Calculate overall batch completion statistics."""
        # Extract logic from mark_batch_completed
        
    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion."""
        # Extract logic from batch_repository_postgres_impl.py lines 466-511
```

**Validation Steps**:
1. Run statistics calculation tests
2. Verify phase statistics accurate
3. Verify aggregations correct
4. Check completion stats
5. Run type checking

### Phase 9: Repository - Extract Mappers

**Objective**: Extract DB↔Domain mapping logic

**New Module: `batch_repository_mappers.py`**
```python
"""Database to domain model mappers for Result Aggregator Service."""

from typing import TYPE_CHECKING, Optional
from datetime import datetime

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.result_aggregator_service.models_db import BatchResult, EssayResult

logger = create_service_logger("result_aggregator.mappers")

class BatchRepositoryMappers:
    """Maps between database models and domain objects."""
    
    def map_batch_to_domain(self, batch: "BatchResult") -> dict:
        """Map BatchResult DB model to domain representation."""
        # Extract mapping logic from various get methods
        
    def map_essay_to_domain(self, essay: "EssayResult") -> dict:
        """Map EssayResult DB model to domain representation."""
        # Extract mapping logic from various get methods
        
    def map_domain_to_batch(self, domain_data: dict) -> dict:
        """Map domain data to BatchResult DB model fields."""
        # Extract mapping logic from create/update methods
        
    def map_domain_to_essay(self, domain_data: dict) -> dict:
        """Map domain data to EssayResult DB model fields."""
        # Extract mapping logic from create/update methods
```

**Validation Steps**:
1. Run mapping tests
2. Verify no data loss in conversions
3. Check all fields mapped correctly
4. Verify datetime handling
5. Run type checking

### Phase 10: Repository - Update Facade Implementation

**Objective**: Create thin facade with session management

**Update: `batch_repository_postgres_impl.py`**
```python
"""PostgreSQL implementation facade for batch repository."""

from typing import TYPE_CHECKING, Optional
from contextlib import asynccontextmanager

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.result_aggregator_service.implementations.batch_repository_mappers import (
    BatchRepositoryMappers,
)
from services.result_aggregator_service.implementations.batch_repository_queries import (
    BatchRepositoryQueries,
)
from services.result_aggregator_service.implementations.batch_statistics_calculator import (
    BatchStatisticsCalculator,
)
from services.result_aggregator_service.implementations.essay_result_updater import (
    EssayResultUpdater,
)

if TYPE_CHECKING:
    from huleedu_service_libs.database import DatabaseMetricsProtocol
    from services.result_aggregator_service.config import Settings
    from services.result_aggregator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.batch_repository")

class BatchRepositoryPostgresImpl(BatchRepositoryProtocol):
    """PostgreSQL implementation facade for batch repository."""
    
    def __init__(
        self,
        settings: "Settings",
        metrics: Optional["DatabaseMetricsProtocol"] = None,
        engine: Optional[AsyncEngine] = None,
    ):
        """Initialize with settings and database engine."""
        self.settings = settings
        self.metrics = metrics
        self.engine = engine or self._create_engine()
        
        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        
        # Initialize components
        self.queries = BatchRepositoryQueries(self.session_factory)
        self.essay_updater = EssayResultUpdater(self.session_factory)
        self.statistics = BatchStatisticsCalculator(self.session_factory)
        self.mappers = BatchRepositoryMappers()
        
    # Delegate all protocol methods to appropriate components
```

**Validation Steps**:
1. Run full repository test suite
2. Verify all operations work
3. Check session management
4. Verify metrics recording
5. Run type checking

### Phase 11: Final Integration and Testing

**Objective**: Ensure complete system works together

**Tasks**:
1. Update DI configuration in `services/result_aggregator_service/di.py`
2. Run full test suite: `pdm run pytest services/result_aggregator_service/tests/`
3. Run type checking: `pdm run typecheck-all`
4. Run linting: `pdm run lint-all`
5. Test Docker containers: `pdm run dev dev result_aggregator`
6. Run E2E scenarios

**Validation Steps**:
1. All unit tests pass
2. All integration tests pass
3. Type checking clean
4. No linting errors
5. Docker containers start successfully
6. E2E scenarios complete successfully
7. Metrics properly recorded
8. Logging working correctly

## Success Criteria

- [ ] No single module exceeds 400 LoC
- [ ] EventProcessorImpl reduced from 761 to ~150 LoC
- [ ] BatchRepositoryPostgresImpl reduced from 761 to ~200 LoC
- [ ] Clear separation of concerns achieved
- [ ] All tests passing
- [ ] Type checking clean
- [ ] Maintains exact protocol compliance
- [ ] Improved testability through focused modules
- [ ] No backwards compatibility code
- [ ] Follows DDD/SRP principles strictly

## Risk Mitigation

1. **Protocol Compliance**: Ensure facades fully implement protocols
2. **Session Management**: Careful handling of async sessions across modules
3. **Transaction Boundaries**: Maintain proper transaction semantics
4. **Test Coverage**: Write tests for each new module before refactoring
5. **Incremental Approach**: Complete one phase at a time with validation

## Notes

- Each phase should be completed in a separate session to avoid overwhelming changes
- Run tests after each phase to ensure nothing breaks
- Use type checking to catch interface mismatches early
- Follow existing patterns from ELS refactoring for consistency