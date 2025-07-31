"""Unit tests for EventProcessorImpl."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events import (
    BatchEssaysRegistered,
    CJAssessmentCompletedV1,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, EssayStatus, ProcessingStage
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    StateStoreProtocol,
)


class MockDIProvider(Provider):
    """Mock dependency injection provider for testing."""

    def __init__(self) -> None:
        super().__init__()
        # Store mocks as instance attributes so they can be accessed
        self.mock_batch_repo = AsyncMock(spec=BatchRepositoryProtocol)
        self.mock_state_store = AsyncMock(spec=StateStoreProtocol)
        self.mock_cache_manager = AsyncMock(spec=CacheManagerProtocol)

    @provide(scope=Scope.REQUEST)
    def provide_batch_repo(self) -> BatchRepositoryProtocol:
        """Provide mock batch repository."""
        return self.mock_batch_repo

    @provide(scope=Scope.REQUEST)
    def provide_state_store(self) -> StateStoreProtocol:
        """Provide mock state store."""
        return self.mock_state_store

    @provide(scope=Scope.REQUEST)
    def provide_cache_manager(self) -> CacheManagerProtocol:
        """Provide mock cache manager."""
        return self.mock_cache_manager

    @provide(scope=Scope.REQUEST)
    def provide_event_processor(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        cache_manager: CacheManagerProtocol,
    ) -> EventProcessorProtocol:
        """Provide the real EventProcessorImpl with mocked dependencies."""
        return EventProcessorImpl(
            batch_repository=batch_repository,
            state_store=state_store,
            cache_manager=cache_manager,
        )


@pytest.fixture
async def test_provider() -> MockDIProvider:
    """Provide test provider instance."""
    return MockDIProvider()


@pytest.fixture
async def di_container(test_provider: MockDIProvider) -> AsyncGenerator[AsyncContainer, None]:
    """Provide a Dishka container with mocked dependencies for testing."""
    container = make_async_container(test_provider)
    yield container
    await container.close()


@pytest.fixture
async def event_processor(di_container: AsyncContainer) -> EventProcessorProtocol:
    """Provide event processor from DI container."""
    async with di_container(scope=Scope.REQUEST) as request_container:
        from typing import cast

        processor = await request_container.get(EventProcessorProtocol)
        return cast(EventProcessorProtocol, processor)


@pytest.fixture
async def mock_batch_repository(test_provider: MockDIProvider) -> AsyncMock:
    """Provide mock batch repository."""
    return test_provider.mock_batch_repo


@pytest.fixture
async def mock_state_store(test_provider: MockDIProvider) -> AsyncMock:
    """Provide mock state store."""
    return test_provider.mock_state_store


@pytest.fixture
async def mock_cache_manager(test_provider: MockDIProvider) -> AsyncMock:
    """Provide mock cache manager."""
    return test_provider.mock_cache_manager


class TestProcessBatchRegistered:
    """Tests for process_batch_registered method."""

    @pytest.mark.asyncio
    async def test_successful_batch_registration(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test successful processing of batch registration event."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())
        essay_count = 5

        # Create proper metadata
        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        data = BatchEssaysRegistered(
            batch_id=batch_id,
            user_id=user_id,
            essay_ids=["essay1", "essay2", "essay3", "essay4", "essay5"],
            expected_essay_count=essay_count,
            metadata=metadata,
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        # Act
        await event_processor.process_batch_registered(envelope, data)

        # Assert
        mock_batch_repository.create_batch.assert_called_once_with(
            batch_id=batch_id, user_id=user_id, essay_count=essay_count, metadata=None
        )
        mock_cache_manager.invalidate_user_batches.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_batch_registration_without_pipelines(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test processing batch registration without requested_pipelines."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())
        essay_count = 3

        # Create proper metadata
        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        data = BatchEssaysRegistered(
            batch_id=batch_id,
            user_id=user_id,
            essay_ids=["essay1", "essay2", "essay3"],
            expected_essay_count=essay_count,
            metadata=metadata,
            course_code=CourseCode.ENG6,
            essay_instructions="Write an essay",
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        # Act
        await event_processor.process_batch_registered(envelope, data)

        # Assert
        mock_batch_repository.create_batch.assert_called_once_with(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=essay_count,
            metadata=None,
        )
        mock_cache_manager.invalidate_user_batches.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_batch_registration_repository_error(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test error handling when repository fails."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())

        # Create proper metadata
        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        data = BatchEssaysRegistered(
            batch_id=batch_id,
            user_id=user_id,
            essay_ids=["essay1", "essay2"],
            expected_essay_count=2,
            metadata=metadata,
            course_code=CourseCode.SV1,
            essay_instructions="Write an essay",
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        mock_batch_repository.create_batch.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await event_processor.process_batch_registered(envelope, data)


class TestProcessBatchPhaseOutcome:
    """Tests for process_batch_phase_outcome method."""

    @pytest.mark.asyncio
    async def test_successful_phase_completion(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing successful phase completion."""
        # Arrange
        batch_id = str(uuid4())

        data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay1", text_storage_id="storage1"),
                EssayProcessingInputRefV1(essay_id="essay2", text_storage_id="storage2"),
                EssayProcessingInputRefV1(essay_id="essay3", text_storage_id="storage3"),
            ],
            failed_essay_ids=[],
            correlation_id=uuid4(),
        )

        envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="ELSBatchPhaseOutcomeV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="els",
            data=data,
        )

        # Act
        await event_processor.process_batch_phase_outcome(envelope, data)

        # Assert
        mock_batch_repository.update_batch_phase_completed.assert_called_once_with(
            batch_id=batch_id,
            phase="spellcheck",
            completed_count=3,
            failed_count=0,
        )
        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_phase_completed_with_failures(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing phase with some failures."""
        # Arrange
        batch_id = str(uuid4())

        data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.CJ_ASSESSMENT,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay1", text_storage_id="storage1"),
                EssayProcessingInputRefV1(essay_id="essay2", text_storage_id="storage2"),
            ],
            failed_essay_ids=["essay3"],
            correlation_id=uuid4(),
        )

        envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="ELSBatchPhaseOutcomeV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="els",
            data=data,
        )

        # Act
        await event_processor.process_batch_phase_outcome(envelope, data)

        # Assert
        mock_batch_repository.update_batch_phase_completed.assert_called_once_with(
            batch_id=batch_id,
            phase="cj_assessment",
            completed_count=2,
            failed_count=1,
        )
        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_critical_phase_failure(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing critical phase failure."""
        # Arrange
        batch_id = str(uuid4())

        data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.FAILED_CRITICALLY,
            processed_essays=[],
            failed_essay_ids=["essay1", "essay2"],
            correlation_id=uuid4(),
        )

        envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="ELSBatchPhaseOutcomeV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="els",
            data=data,
        )

        # Act
        await event_processor.process_batch_phase_outcome(envelope, data)

        # Assert
        # Check that update_batch_failed was called with ErrorDetail and correlation_id
        assert mock_batch_repository.update_batch_failed.call_count == 1
        call_args = mock_batch_repository.update_batch_failed.call_args[1]
        assert call_args["batch_id"] == batch_id
        assert isinstance(call_args["error_detail"], ErrorDetail)
        assert call_args["error_detail"].message == "Phase spellcheck failed critically"
        assert isinstance(call_args["correlation_id"], UUID)
        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_phase_outcome_repository_error(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test error handling when repository fails."""
        # Arrange
        batch_id = str(uuid4())

        data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay1", text_storage_id="storage1"),
            ],
            failed_essay_ids=[],
            correlation_id=uuid4(),
        )

        envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="ELSBatchPhaseOutcomeV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="els",
            data=data,
        )

        mock_batch_repository.update_batch_phase_completed.side_effect = Exception("DB error")

        # Act & Assert
        with pytest.raises(Exception, match="DB error"):
            await event_processor.process_batch_phase_outcome(envelope, data)


class TestProcessSpellcheckCompleted:
    """Tests for process_spellcheck_completed method."""

    @pytest.mark.asyncio
    async def test_successful_spellcheck_with_corrections(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing successful spellcheck with corrected text."""
        # Arrange
        essay_id = str(uuid4())
        batch_id = str(uuid4())
        storage_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        storage_metadata = StorageReferenceMetadata(
            references={
                ContentType.CORRECTED_TEXT: {
                    "main": storage_id,
                }
            }
        )

        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            original_text_storage_id="original_text_123",
            corrections_made=5,
            system_metadata=system_metadata,
            storage_metadata=storage_metadata,
        )

        envelope: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spellchecker",
            data=data,
        )

        # Act
        await event_processor.process_spellcheck_completed(envelope, data)

        # Assert
        # Check the call was made with correct parameters
        assert mock_batch_repository.update_essay_spellcheck_result.call_count == 1
        call_args = mock_batch_repository.update_essay_spellcheck_result.call_args[1]
        assert call_args["essay_id"] == essay_id
        assert call_args["batch_id"] == batch_id
        assert call_args["status"] == ProcessingStage.COMPLETED
        assert call_args["correction_count"] == 5
        assert call_args["corrected_text_storage_id"] == storage_id
        assert call_args["error_detail"] is None
        assert "correlation_id" in call_args
        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_spellcheck_without_corrections(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing spellcheck with no corrections."""
        # Arrange
        essay_id = str(uuid4())
        batch_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            original_text_storage_id="original_text_123",
            corrections_made=0,
            system_metadata=system_metadata,
            storage_metadata=None,
        )

        test_correlation_id = uuid4()
        envelope: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spellchecker",
            correlation_id=test_correlation_id,
            data=data,
        )

        # Act
        await event_processor.process_spellcheck_completed(envelope, data)

        # Assert
        mock_batch_repository.update_essay_spellcheck_result.assert_called_once_with(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStage.COMPLETED,
            correlation_id=test_correlation_id,
            correction_count=0,
            corrected_text_storage_id=None,
            error_detail=None,
        )

    @pytest.mark.asyncio
    async def test_failed_spellcheck(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing failed spellcheck."""
        # Arrange
        essay_id = str(uuid4())
        batch_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            processing_stage=ProcessingStage.FAILED,
            error_info={"message": "Spellcheck service error", "code": "SC_001"},
        )

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
            status=EssayStatus.SPELLCHECK_FAILED,
            original_text_storage_id="original_text_123",
            corrections_made=0,
            system_metadata=system_metadata,
            storage_metadata=None,
        )

        test_correlation_id = uuid4()
        envelope: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spellchecker",
            correlation_id=test_correlation_id,
            data=data,
        )

        # Act
        await event_processor.process_spellcheck_completed(envelope, data)

        # Assert
        # Check that error_detail was created correctly
        call_args = mock_batch_repository.update_essay_spellcheck_result.call_args
        assert call_args.kwargs["essay_id"] == essay_id
        assert call_args.kwargs["batch_id"] == batch_id
        assert call_args.kwargs["status"] == ProcessingStage.FAILED
        assert call_args.kwargs["correction_count"] == 0
        assert call_args.kwargs["corrected_text_storage_id"] is None
        assert call_args.kwargs["error_detail"] is not None
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Verify error_detail structure
        error_detail = call_args.kwargs["error_detail"]
        assert "Spellcheck service error" in error_detail.message
        assert error_detail.error_code.value == "SPELLCHECK_SERVICE_ERROR"

    @pytest.mark.asyncio
    async def test_spellcheck_missing_entity_reference(
        self, event_processor: EventProcessorImpl, mock_batch_repository: AsyncMock
    ) -> None:
        """Test error when entity reference is missing."""
        # Arrange
        # The test wants to simulate missing entity reference in system_metadata
        # Create a minimal system_metadata without entity
        from unittest.mock import Mock

        mock_metadata = Mock(spec=SystemProcessingMetadata)
        mock_metadata.entity = None  # This simulates the missing entity reference

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id="essay1",
            entity_type="essay",
            parent_id=None,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            original_text_storage_id="original_text_123",
            corrections_made=0,
            system_metadata=mock_metadata,
        )

        envelope: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spellchecker",
            data=data,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Missing entity reference"):
            await event_processor.process_spellcheck_completed(envelope, data)

    @pytest.mark.asyncio
    async def test_spellcheck_missing_batch_id(
        self, event_processor: EventProcessorImpl, mock_batch_repository: AsyncMock
    ) -> None:
        """Test error when batch_id is missing in entity reference."""
        # Arrange
        essay_id = str(uuid4())
        # EntityReference removed - testing with missing batch_id (parent_id=None)

        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=None,  # This simulates missing batch_id
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=None,  # Missing batch_id should cause error
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            original_text_storage_id="original_text_123",
            corrections_made=0,
            system_metadata=system_metadata,
        )

        envelope: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spellchecker",
            data=data,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Missing batch_id in entity reference"):
            await event_processor.process_spellcheck_completed(envelope, data)


class TestProcessCJAssessmentCompleted:
    """Tests for process_cj_assessment_completed method."""

    @pytest.mark.asyncio
    async def test_successful_cj_assessment(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing successful CJ assessment results."""
        # Arrange
        batch_id = str(uuid4())
        essay1_id = str(uuid4())
        essay2_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = CJAssessmentCompletedV1(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            cj_assessment_job_id=str(uuid4()),
            rankings=[
                {
                    "els_essay_id": essay1_id,
                    "rank": 1,
                    "score": 0.85,
                },
                {
                    "els_essay_id": essay2_id,
                    "rank": 2,
                    "score": 0.65,
                },
            ],
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
        )

        envelope: EventEnvelope[CJAssessmentCompletedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="CJAssessmentCompletedV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment",
            data=data,
        )

        # Act
        await event_processor.process_cj_assessment_completed(envelope, data)

        # Assert
        assert mock_batch_repository.update_essay_cj_assessment_result.call_count == 2

        # Check first essay
        call_args_1 = mock_batch_repository.update_essay_cj_assessment_result.call_args_list[0]
        assert call_args_1.kwargs["essay_id"] == essay1_id
        assert call_args_1.kwargs["batch_id"] == batch_id
        assert call_args_1.kwargs["status"] == ProcessingStage.COMPLETED
        assert call_args_1.kwargs["rank"] == 1
        assert call_args_1.kwargs["score"] == 0.85
        assert call_args_1.kwargs["comparison_count"] is None
        assert call_args_1.kwargs["error_detail"] is None
        assert "correlation_id" in call_args_1.kwargs

        # Check second essay
        call_args_2 = mock_batch_repository.update_essay_cj_assessment_result.call_args_list[1]
        assert call_args_2.kwargs["essay_id"] == essay2_id
        assert call_args_2.kwargs["batch_id"] == batch_id
        assert call_args_2.kwargs["status"] == ProcessingStage.COMPLETED
        assert call_args_2.kwargs["rank"] == 2
        assert call_args_2.kwargs["score"] == 0.65
        assert call_args_2.kwargs["comparison_count"] is None
        assert call_args_2.kwargs["error_detail"] is None
        assert "correlation_id" in call_args_2.kwargs

        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_cj_assessment_with_missing_essay_id(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test handling ranking without essay_id."""
        # Arrange
        batch_id = str(uuid4())
        essay1_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = CJAssessmentCompletedV1(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            cj_assessment_job_id=str(uuid4()),
            rankings=[
                {
                    "els_essay_id": essay1_id,
                    "rank": 1,
                    "score": 0.85,
                },
                {
                    # Missing els_essay_id
                    "rank": 2,
                    "score": 0.65,
                },
            ],
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
        )

        envelope: EventEnvelope[CJAssessmentCompletedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="CJAssessmentCompletedV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment",
            data=data,
        )

        # Act
        await event_processor.process_cj_assessment_completed(envelope, data)

        # Assert - should only process the first essay
        call_args = mock_batch_repository.update_essay_cj_assessment_result.call_args
        assert call_args.kwargs["essay_id"] == essay1_id
        assert call_args.kwargs["batch_id"] == batch_id
        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED
        assert call_args.kwargs["rank"] == 1
        assert call_args.kwargs["score"] == 0.85
        assert call_args.kwargs["comparison_count"] is None
        assert call_args.kwargs["error_detail"] is None
        assert "correlation_id" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_cj_assessment_empty_rankings(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing CJ assessment with empty rankings."""
        # Arrange
        batch_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = CJAssessmentCompletedV1(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            cj_assessment_job_id=str(uuid4()),
            rankings=[],
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
        )

        envelope: EventEnvelope[CJAssessmentCompletedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="CJAssessmentCompletedV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment",
            data=data,
        )

        # Act
        await event_processor.process_cj_assessment_completed(envelope, data)

        # Assert
        mock_batch_repository.update_essay_cj_assessment_result.assert_not_called()
        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_cj_assessment_repository_error(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test error handling when repository fails."""
        # Arrange
        batch_id = str(uuid4())

        # EntityReference removed - using primitive parameters
        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.COMPLETED,
        )

        data = CJAssessmentCompletedV1(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            cj_assessment_job_id=str(uuid4()),
            rankings=[
                {
                    "els_essay_id": str(uuid4()),
                    "rank": 1,
                    "score": 0.85,
                },
            ],
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
        )

        envelope: EventEnvelope[CJAssessmentCompletedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="CJAssessmentCompletedV1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment",
            data=data,
        )

        mock_batch_repository.update_essay_cj_assessment_result.side_effect = Exception("DB error")

        # Act & Assert
        with pytest.raises(Exception, match="DB error"):
            await event_processor.process_cj_assessment_completed(envelope, data)


# Test Coverage Summary:
# - BatchEssaysRegistered: 3 tests (successful, without pipelines, repository error)
# - ELSBatchPhaseOutcomeV1: 4 tests (successful, with failures, critical failure, repository error)
# - SpellcheckResultDataV1: 5 tests (with corrections, without corrections, failed, missing entity,
#   missing batch_id)
# - CJAssessmentCompletedV1: 4 tests (successful, missing essay_id, empty rankings, repository
#   error)
# Total: 16 tests covering all methods in EventProcessorImpl
