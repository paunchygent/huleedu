"""Test mocks for CJ Assessment Service.

Organized by concern:
- session_mocks: Session provider mocks
- repository_mocks: Per-aggregate repository mocks
- redis_mocks: Redis client mocks
- instruction_store: Instruction storage helper
"""

from services.cj_assessment_service.tests.unit.test_mocks.instruction_store import (
    AssessmentInstructionStore,
)
from services.cj_assessment_service.tests.unit.test_mocks.redis_mocks import MockRedisClient
from services.cj_assessment_service.tests.unit.test_mocks.repository_mocks import (
    MockAnchorRepository,
    MockBatchRepository,
    MockComparisonRepository,
    MockEssayRepository,
    MockGradeProjectionRepository,
    MockInstructionRepository,
)
from services.cj_assessment_service.tests.unit.test_mocks.session_mocks import MockSessionProvider

__all__ = [
    # Session
    "MockSessionProvider",
    # Repositories
    "MockBatchRepository",
    "MockEssayRepository",
    "MockComparisonRepository",
    "MockAnchorRepository",
    "MockInstructionRepository",
    "MockGradeProjectionRepository",
    # Infrastructure
    "MockRedisClient",
    "AssessmentInstructionStore",
]
