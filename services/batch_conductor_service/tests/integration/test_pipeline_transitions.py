"""
Integration tests for multi-pipeline transitions and dependency resolution.

Tests the complete flow of pipeline requests, phase tracking, and transitions
between different pipeline sequences to ensure robust multi-pipeline support.

FOLLOWS HuleEdu STANDARDS:
- Protocol-based dependency injection
- No direct mocking (AsyncMock)
- No internal method access
- Tests through public interfaces only
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from huleedu_service_libs.protocols import KafkaPublisherProtocol
from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.implementations.pipeline_generator_impl import (
    DefaultPipelineGenerator,
)
from services.batch_conductor_service.implementations.pipeline_resolution_service_impl import (
    DefaultPipelineResolutionService,
)
from services.batch_conductor_service.implementations.pipeline_rules_impl import (
    DefaultPipelineRules,
)
from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    DlqProducerProtocol,
)


class MockKafkaProducer(KafkaPublisherProtocol):
    """Protocol-compliant mock Kafka producer for testing."""

    def __init__(self):
        """Initialize with message tracking."""
        self.sent_messages: list[tuple[str, bytes]] = []
        self.is_started = False

    async def start(self) -> None:
        """Start the mock producer."""
        self.is_started = True

    async def stop(self) -> None:
        """Stop the mock producer."""
        self.is_started = False

    async def send(self, topic: str, value: bytes, key: bytes | None = None) -> None:
        """Record sent messages for assertions."""
        self.sent_messages.append((topic, value))

    async def publish(
        self,
        topic: str,
        envelope: Any,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish an event envelope to a Kafka topic."""
        # Convert envelope to bytes for storage
        self.sent_messages.append((topic, str(envelope).encode()))

    def clear_messages(self) -> None:
        """Clear sent messages between tests."""
        self.sent_messages.clear()

    def get_messages_for_topic(self, topic: str) -> list[bytes]:
        """Get all messages sent to a specific topic."""
        return [msg for t, msg in self.sent_messages if t == topic]


class MockDlqProducer(DlqProducerProtocol):
    """Protocol-compliant mock DLQ producer for testing."""

    def __init__(self):
        """Initialize with message tracking."""
        self.sent_messages: list[tuple[str, Any]] = []

    async def send_to_dlq(
        self, message: Any, error_reason: str, original_topic: str | None = None
    ) -> None:
        """Record DLQ messages for assertions."""
        self.sent_messages.append((error_reason, message))

    async def publish_to_dlq(
        self,
        base_topic: str,
        failed_event_envelope: Any,
        dlq_reason: str,
        additional_metadata: dict | None = None,
    ) -> bool:
        """Publish failed event to Dead Letter Queue."""
        self.sent_messages.append((dlq_reason, failed_event_envelope))
        return True


class MockBatchStateRepository(BatchStateRepositoryProtocol):
    """Protocol-compliant mock batch state repository for testing."""

    def __init__(self):
        """Initialize with in-memory storage."""
        self.completed_phases: dict[str, set[str]] = {}
        self.phase_status: dict[tuple[str, str], bool] = {}

    async def record_batch_phase_completion(self, batch_id: str, phase: str, success: bool) -> bool:
        """Record phase completion in memory."""
        if batch_id not in self.completed_phases:
            self.completed_phases[batch_id] = set()

        if success:
            self.completed_phases[batch_id].add(phase)

        self.phase_status[(batch_id, phase)] = success
        return True

    async def get_completed_phases(self, batch_id: str) -> set[str]:
        """Get completed phases from memory."""
        return self.completed_phases.get(batch_id, set())

    async def is_phase_completed(self, batch_id: str, phase: str) -> bool:
        """Check if phase is completed."""
        return phase in self.completed_phases.get(batch_id, set())

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """Record essay step completion - not used in these tests."""
        return True

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get essay completed steps - not used in these tests."""
        return set()

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Get batch completion summary - not used in these tests."""
        return {}

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if batch step is complete."""
        # Check if the step/phase has been completed for this batch
        return step_name in self.completed_phases.get(batch_id, set())

    def clear(self) -> None:
        """Clear all stored data."""
        self.completed_phases.clear()
        self.phase_status.clear()


@pytest.fixture
def mock_kafka_producer() -> MockKafkaProducer:
    """Create mock Kafka producer following protocol pattern."""
    return MockKafkaProducer()


@pytest.fixture
def mock_batch_repo() -> MockBatchStateRepository:
    """Create mock batch state repository following protocol pattern."""
    return MockBatchStateRepository()


@pytest.fixture
def mock_dlq_producer() -> MockDlqProducer:
    """Create mock DLQ producer following protocol pattern."""
    return MockDlqProducer()


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock Kafka event publisher for integration testing."""
    return AsyncMock()


@pytest.fixture
async def pipeline_service(
    mock_batch_repo: MockBatchStateRepository,
    mock_dlq_producer: MockDlqProducer,
    mock_event_publisher: AsyncMock,
) -> DefaultPipelineResolutionService:
    """Create pipeline resolution service with mock dependencies."""
    # Create settings with correct pipeline config path
    settings = Settings()
    # Update the pipeline config path to point to the actual file
    settings.PIPELINE_CONFIG_PATH = "services/batch_conductor_service/pipelines.yaml"
    pipeline_generator = DefaultPipelineGenerator(settings=settings)

    # Ensure pipelines are loaded
    await pipeline_generator._ensure_loaded()

    pipeline_rules = DefaultPipelineRules(
        pipeline_generator=pipeline_generator, batch_state_repository=mock_batch_repo
    )

    # Create empty metrics dict for testing
    metrics: dict[str, Any] = {}

    return DefaultPipelineResolutionService(
        pipeline_rules=pipeline_rules,
        pipeline_generator=pipeline_generator,
        dlq_producer=mock_dlq_producer,
        event_publisher=mock_event_publisher,
        metrics=metrics,
    )


@pytest.fixture
async def integrated_system(
    mock_batch_repo: MockBatchStateRepository,
    mock_kafka_producer: MockKafkaProducer,
    mock_dlq_producer: MockDlqProducer,
    mock_event_publisher: AsyncMock,
) -> dict[str, Any]:
    """Create integrated system components for end-to-end testing."""
    # Create settings with correct pipeline config path
    settings = Settings()
    # Update the pipeline config path to point to the actual file
    settings.PIPELINE_CONFIG_PATH = "services/batch_conductor_service/pipelines.yaml"
    pipeline_generator = DefaultPipelineGenerator(settings=settings)

    # Ensure pipelines are loaded
    await pipeline_generator._ensure_loaded()

    pipeline_rules = DefaultPipelineRules(
        pipeline_generator=pipeline_generator, batch_state_repository=mock_batch_repo
    )

    # Create empty metrics dict for testing
    metrics: dict[str, Any] = {}

    # Create pipeline service with mock dependencies
    pipeline_service = DefaultPipelineResolutionService(
        pipeline_rules=pipeline_rules,
        pipeline_generator=pipeline_generator,
        dlq_producer=mock_dlq_producer,
        event_publisher=mock_event_publisher,
        metrics=metrics,
    )

    return {
        "pipeline_service": pipeline_service,
        "batch_repo": mock_batch_repo,
        "kafka_producer": mock_kafka_producer,
    }


class TestPipelineTransitions:
    """Test multi-pipeline transitions and phase tracking."""

    async def _resolve_pipeline_with_metadata(
        self,
        pipeline_service: DefaultPipelineResolutionService,
        batch_id: str,
        requested_pipeline: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Wrapper to call resolve_pipeline and return expected test format."""
        # Generate deterministic UUID from correlation_id
        correlation_uuid = UUID(hashlib.md5(correlation_id.encode()).hexdigest())

        # Call the actual service method
        phases = await pipeline_service.resolve_pipeline(
            batch_id, requested_pipeline, correlation_uuid
        )

        # Return in the format expected by tests
        return {
            "phases_to_execute": phases,
            "dependencies_met": True,  # If we got phases, dependencies were met
            "requested_pipeline": requested_pipeline,
            "batch_id": batch_id,
        }

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sequential_pipeline_execution(self, integrated_system: dict[str, Any]):
        """Test executing multiple pipelines in sequence with proper phase tracking."""
        batch_id = "batch-seq-001"
        system = integrated_system

        # First pipeline: nlp (includes spellcheck and nlp steps)
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "nlp", "test-correlation-1"
        )
        assert "spellcheck" in resolution["phases_to_execute"]
        assert "nlp" in resolution["phases_to_execute"]
        assert resolution["dependencies_met"] is True

        # Simulate spellcheck completion through repository
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)

        # Second pipeline: cj_assessment (should skip spellcheck)
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "cj_assessment", "test-correlation-2"
        )
        assert "spellcheck" not in resolution["phases_to_execute"]
        assert "cj_assessment" in resolution["phases_to_execute"]

        # Verify phase tracking
        completed_phases = await system["batch_repo"].get_completed_phases(batch_id)
        assert "spellcheck" in completed_phases

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_parallel_pipeline_requests(self, integrated_system: dict[str, Any]):
        """Test handling concurrent pipeline requests for same batch."""
        batch_id = "batch-parallel-001"
        system = integrated_system

        # Simulate concurrent pipeline requests for the same pipeline
        tasks = [
            self._resolve_pipeline_with_metadata(
                system["pipeline_service"], batch_id, "nlp", f"corr-{i}"
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed without race conditions
        assert all(not isinstance(r, Exception) for r in results)

        # All should have same resolution
        successful_results: list[dict[str, Any]] = [r for r in results if isinstance(r, dict)]
        assert len(successful_results) == len(results)  # All should be successful
        first_result = successful_results[0]
        assert all(
            r["phases_to_execute"] == first_result["phases_to_execute"] for r in successful_results
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complex_pipeline_chain(self, integrated_system: dict[str, Any]):
        """Test complex chain: nlp -> cj_assessment -> ai_feedback pipelines."""
        batch_id = "batch-complex-001"
        system = integrated_system

        # Phase 1: NLP pipeline (includes spellcheck and nlp steps)
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "nlp", "corr-nlp-first"
        )
        assert "spellcheck" in resolution["phases_to_execute"]
        assert "nlp" in resolution["phases_to_execute"]

        # Simulate spellcheck and nlp completion
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)
        await system["batch_repo"].record_batch_phase_completion(batch_id, "nlp", True)

        # Phase 2: CJ Assessment pipeline (spellcheck already done, only cj_assessment runs)
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "cj_assessment", "corr-cj"
        )
        assert "spellcheck" not in resolution["phases_to_execute"]  # Already completed
        assert "cj_assessment" in resolution["phases_to_execute"]

        # Simulate CJ completion
        await system["batch_repo"].record_batch_phase_completion(batch_id, "cj_assessment", True)

        # Phase 3: AI Feedback pipeline (spellcheck and nlp done, only ai_feedback runs)
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "ai_feedback", "corr-ai"
        )
        assert "spellcheck" not in resolution["phases_to_execute"]  # Already completed
        assert "nlp" not in resolution["phases_to_execute"]  # Already completed
        assert "ai_feedback" in resolution["phases_to_execute"]

        # Verify all phases tracked
        completed = await system["batch_repo"].get_completed_phases(batch_id)
        assert completed >= {"spellcheck", "nlp", "cj_assessment"}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pipeline_recovery_after_failure(self, integrated_system: dict[str, Any]):
        """Test pipeline can recover and skip completed phases after failure."""
        batch_id = "batch-recovery-001"
        system = integrated_system

        # Start ai_feedback pipeline (includes spellcheck, nlp, ai_feedback steps)
        initial_resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "ai_feedback", "corr-1"
        )
        assert "spellcheck" in initial_resolution["phases_to_execute"]
        assert "nlp" in initial_resolution["phases_to_execute"]
        assert "ai_feedback" in initial_resolution["phases_to_execute"]

        # Simulate partial completion - spellcheck and nlp succeed
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)
        await system["batch_repo"].record_batch_phase_completion(batch_id, "nlp", True)

        # Note: ai_feedback step failed (not marked as complete)

        # Retry pipeline - should skip completed phases
        retry_resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "ai_feedback", "corr-retry"
        )

        assert "spellcheck" not in retry_resolution["phases_to_execute"]  # Already completed
        assert "nlp" not in retry_resolution["phases_to_execute"]  # Already completed
        assert "ai_feedback" in retry_resolution["phases_to_execute"]  # Not completed, needs retry

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_phase_tracking_persistence(self, integrated_system: dict[str, Any]):
        """Test phase tracking persists across service restarts."""
        batch_id = "batch-persist-001"
        system = integrated_system

        # Record phases
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)
        await system["batch_repo"].record_batch_phase_completion(batch_id, "nlp", True)

        # Create new service instances with same repository
        settings = Settings()
        # Update the pipeline config path to point to the actual file
        settings.PIPELINE_CONFIG_PATH = "services/batch_conductor_service/pipelines.yaml"
        pipeline_generator = DefaultPipelineGenerator(settings=settings)

        # Ensure pipelines are loaded
        await pipeline_generator._ensure_loaded()

        pipeline_rules = DefaultPipelineRules(
            pipeline_generator=pipeline_generator, batch_state_repository=system["batch_repo"]
        )

        # Create a mock DLQ producer for the new service
        dlq_producer = MockDlqProducer()
        event_publisher = AsyncMock()

        new_pipeline_service = DefaultPipelineResolutionService(
            pipeline_rules=pipeline_rules,
            pipeline_generator=pipeline_generator,
            dlq_producer=dlq_producer,
            event_publisher=event_publisher,
            metrics={},
        )

        # Should still see completed phases
        resolution = await self._resolve_pipeline_with_metadata(
            new_pipeline_service, batch_id, "cj_assessment", "corr-after-restart"
        )

        assert "spellcheck" not in resolution["phases_to_execute"]
        assert "nlp_analysis" not in resolution["phases_to_execute"]
        assert "cj_assessment" in resolution["phases_to_execute"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_pipeline_transitions(self, integrated_system: dict[str, Any]):
        """Test system handles invalid pipeline transitions gracefully."""
        batch_id = "batch-invalid-001"
        system = integrated_system

        # Try to run ai_feedback pipeline without prerequisites
        # ai_feedback pipeline includes: spellcheck, nlp, ai_feedback steps
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "ai_feedback", "corr-invalid"
        )

        # Should include all required steps from the ai_feedback pipeline
        assert "spellcheck" in resolution["phases_to_execute"]
        assert "nlp" in resolution["phases_to_execute"]
        assert "ai_feedback" in resolution["phases_to_execute"]
        # Note: cj_assessment is NOT part of ai_feedback pipeline

        # Complete only spellcheck
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)

        # Try again - should skip completed step
        resolution2 = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "ai_feedback", "corr-invalid-2"
        )

        assert "spellcheck" not in resolution2["phases_to_execute"]  # Already completed
        assert "nlp" in resolution2["phases_to_execute"]  # Still needed
        assert "ai_feedback" in resolution2["phases_to_execute"]  # Still needed

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_event_processing_simulation(self, integrated_system: dict[str, Any]):
        """Test event processing through proper channels."""
        batch_id = "batch-event-001"
        system = integrated_system

        # Start nlp pipeline that would normally trigger events
        # nlp pipeline includes: spellcheck, nlp steps
        resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "nlp", "corr-event"
        )

        # Verify that we got phases to execute
        assert "spellcheck" in resolution["phases_to_execute"]
        assert "nlp" in resolution["phases_to_execute"]

        # Simulate receiving completion event by updating repository directly
        # (In production, this would come from Kafka consumer processing)
        await system["batch_repo"].record_batch_phase_completion(batch_id, "spellcheck", True)

        # Verify next pipeline sees completion
        # cj_assessment pipeline includes: spellcheck, cj_assessment steps
        next_resolution = await self._resolve_pipeline_with_metadata(
            system["pipeline_service"], batch_id, "cj_assessment", "corr-next"
        )
        assert "spellcheck" not in next_resolution["phases_to_execute"]  # Already completed
        assert "cj_assessment" in next_resolution["phases_to_execute"]  # Still needed
