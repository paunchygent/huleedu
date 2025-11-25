"""Unit tests for identity threading in batch preparation workflow.

This module tests the identity field extraction and propagation through the
batch creation process, ensuring user_id and org_id are correctly passed
from request data to database operations for credit attribution.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from pytest import FixtureRequest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import batch_preparation
from services.cj_assessment_service.cj_core_logic.batch_preparation import create_cj_batch
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import CJAssessmentRequestData, EssayToProcess
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    ContentClientProtocol,
    SessionProviderProtocol,
)


class TestIdentityThreadingInBatchCreation:
    """Tests for identity field threading through batch creation process."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol with identity field support."""
        mock_db = AsyncMock()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_batch = Mock(spec=CJBatchUpload)
        mock_batch.id = 12345
        mock_batch.processing_metadata = {}
        mock_batch.assignment_id = None

        # Mock session context manager
        mock_db.session.return_value.__aenter__.return_value = mock_session
        mock_db.session.return_value.__aexit__.return_value = None

        # Mock batch creation with identity parameters
        mock_db.create_new_cj_batch.return_value = mock_batch

        # Mock assessment instruction lookup to return None by default
        mock_db.get_assessment_instruction.return_value = None

        return mock_db

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client protocol."""
        return AsyncMock(spec=ContentClientProtocol)

    @pytest.fixture
    def mock_session_provider(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock session provider that yields mock_database's session."""
        provider = AsyncMock()
        # Get the mock session that mock_database.session() would yield
        mock_session_obj = mock_database.session.return_value.__aenter__.return_value

        @asynccontextmanager
        async def mock_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session_obj

        provider.session = mock_session
        return provider

    @pytest.fixture
    def mock_batch_repository(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock batch repository that delegates to mock_database."""
        mock_repo = AsyncMock()
        mock_repo.create_new_cj_batch = mock_database.create_new_cj_batch
        return mock_repo

    @pytest.fixture
    def mock_instruction_repository(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock instruction repository that delegates to mock_database."""
        mock_repo = AsyncMock()
        mock_repo.get_assessment_instruction = mock_database.get_assessment_instruction
        return mock_repo

    @pytest.fixture(autouse=True)
    def patch_metadata_merges(
        self,
        request: FixtureRequest,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Patch metadata merge helpers to capture payloads during tests."""

        if "mock_database" not in request.fixturenames:
            return

        mock_database: AsyncMock = request.getfixturevalue("mock_database")
        captured_uploads: list[dict[str, Any]] = []
        captured_state: list[dict[str, Any]] = []

        async def fake_merge_batch_upload_metadata(
            *,
            session_provider: SessionProviderProtocol,
            cj_batch_id: int,
            metadata_updates: dict[str, Any],
            correlation_id: Any,
        ) -> None:
            captured_uploads.append(metadata_updates)
            target = mock_database.create_new_cj_batch.return_value
            existing = target.processing_metadata or {}
            target.processing_metadata = {**existing, **metadata_updates}

        async def fake_merge_batch_processing_metadata(
            *,
            session_provider: SessionProviderProtocol,
            cj_batch_id: int,
            metadata_updates: dict[str, Any],
            correlation_id: Any,
        ) -> None:
            captured_state.append(metadata_updates)

        monkeypatch.setattr(
            batch_preparation,
            "merge_batch_upload_metadata",
            fake_merge_batch_upload_metadata,
        )
        monkeypatch.setattr(
            batch_preparation,
            "merge_batch_processing_metadata",
            fake_merge_batch_processing_metadata,
        )

        mock_database.captured_upload_metadata = captured_uploads
        mock_database.captured_state_metadata = captured_state

    @staticmethod
    def _build_metric_counters() -> tuple[SimpleNamespace, SimpleNamespace]:
        """Create counters emulating minimal Prometheus Counter API."""

        class Counter(SimpleNamespace):
            def __init__(self) -> None:
                super().__init__(count=0)

            def inc(self) -> None:
                self.count += 1

        class LabelledCounter(Counter):
            def __init__(self) -> None:
                super().__init__()
                self.labels_calls: list[dict[str, str]] = []

            def labels(self, **labels: str) -> "LabelledCounter":
                self.labels_calls.append(labels)
                return self

        return Counter(), LabelledCounter()

    @pytest.fixture
    def base_request_data(self) -> dict[str, Any]:
        """Provide base request data structure."""
        return {
            "bos_batch_id": "test-batch-123",
            "language": "en",
            "course_code": "ENG5",
            "student_prompt_text": "Compare essay quality",
            "student_prompt_storage_id": "prompt-storage-base",
            "judge_rubric_text": "Judge rubric baseline",
            "judge_rubric_storage_id": "rubric-storage-base",
            "essays_to_process": [
                {"els_essay_id": "essay1", "text_storage_id": "storage1"},
                {"els_essay_id": "essay2", "text_storage_id": "storage2"},
            ],
            "assignment_id": "assignment-456",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, expected_user_id, expected_org_id, description",
        [
            # Standard case: both user_id and org_id provided
            ("user-123", "org-456", "user-123", "org-456", "Both user_id and org_id provided"),
            # Optional org_id case: org_id is None
            ("user-789", None, "user-789", None, "User ID provided, org_id is None"),
            # Edge case: empty string org_id (treated as None by database)
            ("user-abc", "", "user-abc", "", "User ID provided, empty string org_id"),
            # Swedish characters in user identity
            (
                "användar-åäö123",
                "organisation-ÅÄÖ456",
                "användar-åäö123",
                "organisation-ÅÄÖ456",
                "Swedish characters in identity fields",
            ),
            # UUID-style identifiers (common pattern)
            (
                str(uuid4()),
                str(uuid4()),
                None,  # Will be set dynamically in test
                None,  # Will be set dynamically in test
                "UUID-style identity identifiers",
            ),
        ],
    )
    async def test_identity_extraction_and_database_storage(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
        user_id: str,
        org_id: str | None,
        expected_user_id: str | None,
        expected_org_id: str | None,
        description: str,
    ) -> None:
        """Test identity field extraction from request_data and storage in database.

        Verifies that user_id and org_id are correctly extracted from request_data
        (lines 55-56) and passed to create_new_cj_batch method (lines 71-72).
        """
        # Arrange - Handle UUID case dynamically
        if description == "UUID-style identity identifiers":
            expected_user_id = user_id
            expected_org_id = org_id

        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            user_id=user_id,
            org_id=org_id,
        )
        correlation_id = uuid4()
        log_extra = {"test": "identity_threading"}

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=correlation_id,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra=log_extra,
        )

        # Assert - Verify behavioral outcomes
        assert cj_batch_id == 12345

        # Verify create_new_cj_batch called with correct identity parameters
        mock_database.create_new_cj_batch.assert_called_once()
        call_args = mock_database.create_new_cj_batch.call_args

        # Verify identity fields are passed correctly (lines 71-72 behavior)
        assert call_args.kwargs["user_id"] == expected_user_id
        assert call_args.kwargs["org_id"] == expected_org_id

        # Verify other parameters are correctly extracted and passed
        assert (
            call_args.kwargs["session"]
            == mock_database.session.return_value.__aenter__.return_value
        )
        assert call_args.kwargs["bos_batch_id"] == "test-batch-123"
        assert call_args.kwargs["event_correlation_id"] == str(correlation_id)
        assert call_args.kwargs["language"] == "en"
        assert call_args.kwargs["course_code"] == "ENG5"
        assert call_args.kwargs["initial_status"] == CJBatchStatusEnum.PENDING
        assert call_args.kwargs["expected_essay_count"] == 2
        assert (
            mock_database.create_new_cj_batch.return_value.processing_metadata[
                "student_prompt_storage_id"
            ]
            == "prompt-storage-base"
        )
        assert (
            mock_database.create_new_cj_batch.return_value.processing_metadata[
                "student_prompt_text"
            ]
            == "Compare essay quality"
        )
        assert (
            mock_database.create_new_cj_batch.return_value.processing_metadata[
                "judge_rubric_storage_id"
            ]
            == "rubric-storage-base"
        )
        assert (
            mock_database.create_new_cj_batch.return_value.processing_metadata["judge_rubric_text"]
            == "Judge rubric baseline"
        )

        assert getattr(mock_database, "captured_upload_metadata", []), "metadata merge not recorded"
        latest_metadata = mock_database.captured_upload_metadata[-1]
        assert "original_request" in latest_metadata
        assert latest_metadata["original_request"]["language"] == "en"

    @pytest.mark.asyncio
    async def test_missing_user_id_validation(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
    ) -> None:
        """Test behavior when user_id is missing from request_data."""
        # Arrange - Request data without user_id
        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            org_id="org-123",
        )
        correlation_id = uuid4()
        log_extra = {"test": "missing_user_id"}

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=correlation_id,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra=log_extra,
        )

        # Assert - Verify None user_id is passed to database
        assert cj_batch_id == 12345
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] is None
        assert call_args.kwargs["org_id"] == "org-123"

    @pytest.mark.asyncio
    async def test_missing_required_fields_with_identity_fields_present(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
    ) -> None:
        """Test ValueError when bos_batch_id missing but identity fields present."""
        # Arrange - Create a minimal request without bos_batch_id (will fail validation)
        # Note: CJAssessmentRequestData requires bos_batch_id, so we test with inadequate data
        correlation_id = uuid4()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await create_cj_batch(
                request_data=CJAssessmentRequestData(
                    bos_batch_id="",  # Empty to trigger error
                    assignment_id="test-assign",
                    language="en",
                    course_code="ENG5",
                    essays_to_process=[
                        EssayToProcess(els_essay_id="essay1", text_storage_id="storage1")
                    ],
                    student_prompt_text="Compare essays",
                    user_id="user-123",
                    org_id="org-456",
                ),
                correlation_id=correlation_id,
                session_provider=mock_session_provider,
                batch_repository=mock_batch_repository,
                instruction_repository=mock_instruction_repository,
                content_client=mock_content_client,
                log_extra={},
            )

        assert "Missing required fields: bos_batch_id or essays_to_process" in str(exc_info.value)
        mock_database.create_new_cj_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_cj_batch_hydrates_prompt_with_fallback(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        base_request_data: dict[str, Any],
    ) -> None:
        """Fallback hydration populates metadata and increments success metric."""

        success_counter, failure_counter = self._build_metric_counters()
        mock_batch = mock_database.create_new_cj_batch.return_value
        mock_batch.processing_metadata = {"retry_count": 2}
        monkeypatch.setattr(
            batch_preparation,
            "get_business_metrics",
            lambda: {
                "prompt_fetch_success": success_counter,
                "prompt_fetch_failures": failure_counter,
            },
        )

        mock_content_client.fetch_content.return_value = "Hydrated prompt body"

        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=None,
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
        )

        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        assert cj_batch_id == 12345
        metadata = mock_batch.processing_metadata
        assert metadata["student_prompt_storage_id"] == "prompt-storage-base"
        assert metadata["student_prompt_text"] == "Hydrated prompt body"
        assert metadata["judge_rubric_storage_id"] == "rubric-storage-base"
        assert metadata["judge_rubric_text"] == "Judge rubric baseline"
        assert metadata["retry_count"] == 2
        assert success_counter.count == 1
        assert failure_counter.count == 0

    @pytest.mark.asyncio
    async def test_create_cj_batch_records_metric_on_fallback_failure(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        base_request_data: dict[str, Any],
    ) -> None:
        """Fallback failure emits labelled failure metric without clobbering metadata."""

        success_counter, failure_counter = self._build_metric_counters()
        mock_batch = mock_database.create_new_cj_batch.return_value
        mock_batch.processing_metadata = {"retry_count": 2}
        monkeypatch.setattr(
            batch_preparation,
            "get_business_metrics",
            lambda: {
                "prompt_fetch_success": success_counter,
                "prompt_fetch_failures": failure_counter,
            },
        )

        mock_content_client.fetch_content.side_effect = RuntimeError("boom")

        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=None,
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
        )

        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        assert cj_batch_id == 12345
        metadata = mock_batch.processing_metadata
        assert metadata["student_prompt_storage_id"] == "prompt-storage-base"
        assert "student_prompt_text" not in metadata
        assert metadata["judge_rubric_storage_id"] == "rubric-storage-base"
        assert metadata["judge_rubric_text"] == "Judge rubric baseline"
        assert metadata["retry_count"] == 2
        assert success_counter.count == 0
        assert failure_counter.count == 1
        assert failure_counter.labels_calls == [{"reason": "batch_creation_hydration_failed"}]

    @pytest.mark.asyncio
    async def test_create_cj_batch_hydrates_judge_rubric_text_when_missing(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
        base_request_data: dict[str, Any],
    ) -> None:
        """Judge rubric text should be hydrated when storage reference exists."""

        mock_batch = mock_database.create_new_cj_batch.return_value
        mock_batch.processing_metadata = {}
        mock_content_client.fetch_content = AsyncMock(side_effect=["Hydrated rubric guidance"])

        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=None,
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
        )

        await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        metadata = mock_batch.processing_metadata
        assert metadata["judge_rubric_storage_id"] == "rubric-storage-base"
        assert metadata["judge_rubric_text"] == "Hydrated rubric guidance"
        mock_content_client.fetch_content.assert_awaited_once_with("rubric-storage-base", ANY)

    @pytest.mark.asyncio
    async def test_identity_field_precedence_over_defaults(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
    ) -> None:
        """Test that explicit identity fields are passed through correctly."""
        # Arrange
        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            user_id="explicit-user-999",
            org_id="explicit-org-888",
        )

        # Act
        await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] == "explicit-user-999"
        assert call_args.kwargs["org_id"] == "explicit-org-888"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id_value, org_id_value, description",
        [
            # Whitespace handling
            (
                "  user-with-spaces  ",
                "  org-with-spaces  ",
                "Values with leading/trailing whitespace",
            ),
            # Special characters in identifiers
            ("user@example.com", "org.subdomain.com", "Email-style and domain-style identifiers"),
            # Numeric string identifiers
            ("12345", "67890", "Numeric string identifiers"),
            # Mixed case handling
            ("User-Mixed-Case", "Org-Mixed-Case", "Mixed case identifiers"),
        ],
    )
    async def test_identity_field_edge_cases(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
        user_id_value: str,
        org_id_value: str,
        description: str,
    ) -> None:
        """Test various edge cases in identity field values."""
        # Arrange
        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id=base_request_data["assignment_id"],
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            user_id=user_id_value,
            org_id=org_id_value,
        )

        # Act
        await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] == user_id_value
        assert call_args.kwargs["org_id"] == org_id_value

    @pytest.mark.asyncio
    async def test_assignment_id_storage_with_identity_fields(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
    ) -> None:
        """Test assignment_id storage works alongside identity field processing."""
        # Arrange
        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id="test-assignment-789",
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            user_id="user-with-assignment",
            org_id="org-with-assignment",
        )
        mock_batch = Mock(spec=CJBatchUpload)
        mock_batch.id = 99999
        mock_batch.processing_metadata = {}
        mock_database.create_new_cj_batch.return_value = mock_batch
        mock_session = mock_database.session.return_value.__aenter__.return_value

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        assert cj_batch_id == 99999
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] == "user-with-assignment"
        assert call_args.kwargs["org_id"] == "org-with-assignment"
        assert mock_batch.assignment_id == "test-assignment-789"
        assert mock_session.flush.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_identity_threading_workflow(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        base_request_data: dict[str, Any],
        mock_content_client: AsyncMock,
    ) -> None:
        """Test complete identity threading workflow with comprehensive validation."""
        # Arrange
        request_data = CJAssessmentRequestData(
            bos_batch_id=base_request_data["bos_batch_id"],
            assignment_id="comprehensive-assignment",
            language=base_request_data["language"],
            course_code=base_request_data["course_code"],
            essays_to_process=[
                EssayToProcess(
                    els_essay_id=essay["els_essay_id"],
                    text_storage_id=essay["text_storage_id"],
                )
                for essay in base_request_data["essays_to_process"]
            ],
            student_prompt_text=base_request_data.get("student_prompt_text"),
            student_prompt_storage_id=base_request_data.get("student_prompt_storage_id"),
            judge_rubric_text=base_request_data.get("judge_rubric_text"),
            judge_rubric_storage_id=base_request_data.get("judge_rubric_storage_id"),
            user_id="comprehensive-user-åäö",
            org_id="comprehensive-org-ÅÄÖ",
        )
        correlation_id = uuid4()

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=correlation_id,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        assert cj_batch_id == 12345
        call_args = mock_database.create_new_cj_batch.call_args

        # Verify identity field extraction and propagation
        assert call_args.kwargs["user_id"] == "comprehensive-user-åäö"
        assert call_args.kwargs["org_id"] == "comprehensive-org-ÅÄÖ"
        assert call_args.kwargs["bos_batch_id"] == "test-batch-123"
        assert call_args.kwargs["event_correlation_id"] == str(correlation_id)
        assert call_args.kwargs["expected_essay_count"] == 2

        # Verify assignment_id handling
        created_batch = mock_database.create_new_cj_batch.return_value
        assert created_batch.assignment_id == "comprehensive-assignment"


class TestIdentityFieldDefaultBehavior:
    """Tests for default behavior when identity fields are not provided."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol."""
        mock_db = AsyncMock()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_batch = Mock(spec=CJBatchUpload)
        mock_batch.id = 54321
        mock_batch.processing_metadata = {}
        mock_batch.assignment_id = None

        mock_db.session.return_value.__aenter__.return_value = mock_session
        mock_db.session.return_value.__aexit__.return_value = None
        mock_db.create_new_cj_batch.return_value = mock_batch

        # Mock assessment instruction lookup to return None by default
        mock_db.get_assessment_instruction.return_value = None

        return mock_db

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client protocol."""
        return AsyncMock(spec=ContentClientProtocol)

    @pytest.fixture
    def mock_session_provider(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock session provider that yields mock_database's session."""
        provider = AsyncMock()
        # Get the mock session that mock_database.session() would yield
        mock_session_obj = mock_database.session.return_value.__aenter__.return_value

        @asynccontextmanager
        async def mock_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session_obj

        provider.session = mock_session
        return provider

    @pytest.fixture
    def mock_batch_repository(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock batch repository that delegates to mock_database."""
        mock_repo = AsyncMock()
        mock_repo.create_new_cj_batch = mock_database.create_new_cj_batch
        return mock_repo

    @pytest.fixture
    def mock_instruction_repository(self, mock_database: AsyncMock) -> AsyncMock:
        """Create mock instruction repository that delegates to mock_database."""
        mock_repo = AsyncMock()
        mock_repo.get_assessment_instruction = mock_database.get_assessment_instruction
        return mock_repo

    @pytest.mark.asyncio
    async def test_no_identity_fields_in_request_data(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
    ) -> None:
        """Test behavior when no identity fields are present in request_data."""
        # Arrange
        mock_database.get_assessment_instruction.return_value = None

        request_data = CJAssessmentRequestData(
            bos_batch_id="no-identity-batch",
            language="sv",
            course_code="SV1",
            student_prompt_text="Jämför uppsatserna",
            essays_to_process=[EssayToProcess(els_essay_id="essay1", text_storage_id="storage1")],
            assignment_id="no-identity-assignment",
        )

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        assert cj_batch_id == 54321
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] is None
        assert call_args.kwargs["org_id"] is None
        assert call_args.kwargs["bos_batch_id"] == "no-identity-batch"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, description",
        [
            # Partial identity cases
            ("partial-user", None, "Only user_id provided, org_id None"),
            (None, "partial-org", "Only org_id provided, user_id None"),
            (None, None, "Both identity fields explicitly None"),
        ],
    )
    async def test_partial_identity_field_scenarios(
        self,
        mock_database: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_instruction_repository: AsyncMock,
        mock_content_client: AsyncMock,
        user_id: str | None,
        org_id: str | None,
        description: str,
    ) -> None:
        """Test scenarios with partial or null identity field values."""
        # Arrange
        request_data = CJAssessmentRequestData(
            bos_batch_id="partial-identity-batch",
            language="en",
            course_code="ENG3",
            student_prompt_text="Compare these essays",
            essays_to_process=[EssayToProcess(els_essay_id="essay1", text_storage_id="storage1")],
            assignment_id="partial-identity-assignment",
            user_id=user_id,
            org_id=org_id,
        )

        # Act
        cj_batch_id = await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            instruction_repository=mock_instruction_repository,
            content_client=mock_content_client,
            log_extra={},
        )

        # Assert
        assert cj_batch_id == 54321
        call_args = mock_database.create_new_cj_batch.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["org_id"] == org_id
