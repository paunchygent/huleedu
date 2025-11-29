"""
Real integration tests for system prompt hierarchy validation.

These tests validate the complete system prompt hierarchy through actual code paths:
1. Event-level override (highest priority)
2. CJ Assessment default (middle priority)
3. LLM Provider fallback (unreachable for CJ workflows)

Tests use:
- Real PostgreSQL database (testcontainers)
- Real CJ Assessment service components
- Real data flow through entire stack
- Mocked HTTP calls to LLM Provider Service (captures actual request payloads)
"""

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aioresponses import aioresponses
from common_core.events.cj_assessment_events import LLMConfigOverrides

from services.cj_assessment_service.cj_core_logic.comparison_processing import (
    submit_comparisons_for_async_processing,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
    EssayToProcess,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)

pytest_plugins = [
    "services.cj_assessment_service.tests.integration.llm_payload_fixtures",
]

if TYPE_CHECKING:
    from .llm_payload_fixtures import CapturedRequestExtractor
else:  # pragma: no cover - runtime fallback for postponed evaluation
    CapturedRequestExtractor = Any

# ==================== Test Class ====================


@pytest.mark.asyncio
class TestSystemPromptHierarchyIntegration:
    """Integration tests for system prompt hierarchy through real code paths."""

    async def test_event_level_override_captured_in_http_request(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        mock_content_client: ContentClientProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_matching_strategy: MagicMock,
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Verify event-level system prompt override is sent in HTTP request.

        Tests: Hierarchy Level 1 (Event Override - Highest Priority)

        Flow:
        1. Create batch with explicit system_prompt_override in event
        2. Process through real comparison_processing
        3. Capture HTTP request to LLM Provider Service
        4. Verify custom prompt in request body
        """
        # Unpack fixture
        llm_interaction, http_mocker = real_llm_interaction

        # Arrange: Create batch with custom system prompt override
        custom_prompt = "CUSTOM EVENT-LEVEL SYSTEM PROMPT - HIGHEST PRIORITY TEST"

        async with postgres_session_provider.session() as session:
            # Create real batch in database
            batch = await postgres_batch_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid.uuid4()),
                event_correlation_id=str(uuid.uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=2,
            )
            await session.commit()
            cj_batch_id = batch.id

        # Create sample essays for comparison
        essays = [
            EssayForComparison(
                id="event-override-essay-1",
                text_content="This is a well-structured essay with clear arguments and evidence.",
                current_bt_score=0.0,
            ),
            EssayForComparison(
                id="event-override-essay-2",
                text_content="This essay presents ideas but lacks organizational clarity.",
                current_bt_score=0.0,
            ),
        ]

        # Persist essays to database (required before creating comparison pairs)
        async with postgres_session_provider.session() as session:
            for essay in essays:
                await postgres_essay_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=essay.id,
                    text_storage_id=f"storage-{essay.id}",
                    assessment_input_text=essay.text_content,
                )
            await session.commit()

        # Request data with explicit override
        request_data = CJAssessmentRequestData(
            bos_batch_id=str(uuid.uuid4()),
            assignment_id="test-assign",
            essays_to_process=[
                EssayToProcess(els_essay_id=essay.id, text_storage_id=f"storage-{essay.id}")
                for essay in essays
            ],
            language="en",
            course_code="ENG5",
            llm_config_overrides=LLMConfigOverrides(
                system_prompt_override=custom_prompt,
            ),
        )

        # Act: Process through real code path
        await submit_comparisons_for_async_processing(
            essays_for_api_model=essays,
            cj_batch_id=cj_batch_id,
            session_provider=postgres_session_provider,
            batch_repository=postgres_batch_repository,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            request_data=request_data,
            llm_interaction=llm_interaction,
            matching_strategy=mock_matching_strategy,
            settings=test_settings,
            correlation_id=uuid.uuid4(),
            log_extra={"test": "event_override"},
        )

        # Assert: Extract captured requests from mocker
        captured_http_requests = capture_requests_from_mocker(http_mocker)
        assert len(captured_http_requests) > 0, "No HTTP requests captured"

        http_request = captured_http_requests[0]
        assert "llm_config_overrides" in http_request
        assert "system_prompt_override" in http_request["llm_config_overrides"]

        actual_prompt = http_request["llm_config_overrides"]["system_prompt_override"]
        assert actual_prompt == custom_prompt, f"Expected custom prompt but got: {actual_prompt}"
        assert actual_prompt != test_settings.SYSTEM_PROMPT, (
            "Custom override should differ from CJ default"
        )

    async def test_cj_default_system_prompt_when_no_override(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        mock_content_client: ContentClientProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_matching_strategy: MagicMock,
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Verify CJ default system prompt is used when no override provided.

        Tests: Hierarchy Level 2 (CJ Assessment Default - Middle Priority)

        Flow:
        1. Create batch with NO llm_config_overrides
        2. Process through real comparison_processing
        3. Capture HTTP request
        4. Verify settings.SYSTEM_PROMPT in request body
        """
        # Unpack fixture
        llm_interaction, http_mocker = real_llm_interaction

        # Arrange: Create batch without override
        async with postgres_session_provider.session() as session:
            batch = await postgres_batch_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid.uuid4()),
                event_correlation_id=str(uuid.uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=2,
            )
            await session.commit()
            cj_batch_id = batch.id

        essays = [
            EssayForComparison(
                id="no-override-essay-1",
                text_content="Strong analytical essay with logical progression and evidence.",
                current_bt_score=0.0,
            ),
            EssayForComparison(
                id="no-override-essay-2",
                text_content="Essay with developing ideas and moderate organization.",
                current_bt_score=0.0,
            ),
        ]

        # Persist essays to database (required before creating comparison pairs)
        async with postgres_session_provider.session() as session:
            for essay in essays:
                await postgres_essay_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=essay.id,
                    text_storage_id=f"storage-{essay.id}",
                    assessment_input_text=essay.text_content,
                )
            await session.commit()

        # Request data with NO override
        request_data = CJAssessmentRequestData(
            bos_batch_id=str(uuid.uuid4()),
            assignment_id="test-assign",
            essays_to_process=[
                EssayToProcess(els_essay_id=essay.id, text_storage_id=f"storage-{essay.id}")
                for essay in essays
            ],
            language="en",
            course_code="ENG5",
            llm_config_overrides=None,  # No override at all
        )

        # Act
        await submit_comparisons_for_async_processing(
            essays_for_api_model=essays,
            cj_batch_id=cj_batch_id,
            session_provider=postgres_session_provider,
            batch_repository=postgres_batch_repository,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            request_data=request_data,
            llm_interaction=llm_interaction,
            matching_strategy=mock_matching_strategy,
            settings=test_settings,
            correlation_id=uuid.uuid4(),
            log_extra={"test": "no_override"},
        )

        # Assert: Extract captured requests from mocker
        captured_http_requests = capture_requests_from_mocker(http_mocker)
        assert len(captured_http_requests) > 0

        http_request = captured_http_requests[0]
        actual_prompt = http_request["llm_config_overrides"]["system_prompt_override"]

        assert actual_prompt == test_settings.SYSTEM_PROMPT, (
            "Should use CJ default when no override provided"
        )
        assert "impartial Comparative Judgement assessor" in actual_prompt
        assert "Constraints:" in actual_prompt
        assert "confidence" in actual_prompt.lower()

    async def test_none_override_falls_back_to_cj_default(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        mock_content_client: ContentClientProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_matching_strategy: MagicMock,
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Verify None override doesn't bypass CJ default.

        Tests: Conditional override logic (only override if not None)

        Flow:
        1. Create batch with system_prompt_override=None (explicit None)
        2. Process through real code
        3. Verify CJ default is used (not None sent to HTTP)
        """
        # Unpack fixture
        llm_interaction, http_mocker = real_llm_interaction

        # Arrange
        async with postgres_session_provider.session() as session:
            batch = await postgres_batch_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid.uuid4()),
                event_correlation_id=str(uuid.uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=2,
            )
            await session.commit()
            cj_batch_id = batch.id

        essays = [
            EssayForComparison(
                id="none-override-essay-1",
                text_content="Comprehensive essay demonstrating deep analysis and clear structure.",
                current_bt_score=0.0,
            ),
            EssayForComparison(
                id="none-override-essay-2",
                text_content="Basic essay with limited development and weak organization.",
                current_bt_score=0.0,
            ),
        ]

        # Persist essays to database (required before creating comparison pairs)
        async with postgres_session_provider.session() as session:
            for essay in essays:
                await postgres_essay_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=essay.id,
                    text_storage_id=f"storage-{essay.id}",
                    assessment_input_text=essay.text_content,
                )
            await session.commit()

        # Request data with explicit None override (e.g., ENG5 --no-cj-system-prompt)
        request_data = CJAssessmentRequestData(
            bos_batch_id=str(uuid.uuid4()),
            assignment_id="test-assign",
            essays_to_process=[
                EssayToProcess(els_essay_id=essay.id, text_storage_id=f"storage-{essay.id}")
                for essay in essays
            ],
            language="en",
            course_code="ENG5",
            llm_config_overrides=LLMConfigOverrides(
                model_override="gpt-4o",  # Other overrides present
                temperature_override=0.3,
                system_prompt_override=None,  # Explicit None
            ),
        )

        # Act
        await submit_comparisons_for_async_processing(
            essays_for_api_model=essays,
            cj_batch_id=cj_batch_id,
            session_provider=postgres_session_provider,
            batch_repository=postgres_batch_repository,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            request_data=request_data,
            llm_interaction=llm_interaction,
            matching_strategy=mock_matching_strategy,
            settings=test_settings,
            correlation_id=uuid.uuid4(),
            log_extra={"test": "none_override"},
        )

        # Assert: Extract captured requests from mocker
        captured_http_requests = capture_requests_from_mocker(http_mocker)
        assert len(captured_http_requests) > 0

        http_request = captured_http_requests[0]
        actual_prompt = http_request["llm_config_overrides"]["system_prompt_override"]

        assert actual_prompt is not None, "Should not send None to HTTP endpoint"
        assert actual_prompt == test_settings.SYSTEM_PROMPT, (
            "None override should fall back to CJ default"
        )

    async def test_system_prompt_header_structure_coherence(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_essay_repository: CJEssayRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        mock_content_client: ContentClientProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_matching_strategy: MagicMock,
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Verify system prompt and user prompt structure is coherent.

        Tests: Combined prompt structure sent to LLM Provider

        Validates:
        - system_prompt_override field exists and has role definition
        - user_prompt field exists and has essay comparison content
        - No conflicting header levels between prompts
        """
        # Unpack fixture
        llm_interaction, http_mocker = real_llm_interaction

        # Arrange
        async with postgres_session_provider.session() as session:
            batch = await postgres_batch_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid.uuid4()),
                event_correlation_id=str(uuid.uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=2,
            )
            await session.commit()
            cj_batch_id = batch.id

        essays = [
            EssayForComparison(
                id="header-test-essay-1",
                text_content="Essay A with detailed analysis and clear structure.",
                current_bt_score=0.0,
            ),
            EssayForComparison(
                id="header-test-essay-2",
                text_content="Essay B with basic content and less organization.",
                current_bt_score=0.0,
            ),
        ]

        # Persist essays to database (required before creating comparison pairs)
        async with postgres_session_provider.session() as session:
            for essay in essays:
                await postgres_essay_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=essay.id,
                    text_storage_id=f"storage-{essay.id}",
                    assessment_input_text=essay.text_content,
                )
            await session.commit()

        request_data = CJAssessmentRequestData(
            bos_batch_id=str(uuid.uuid4()),
            assignment_id="test-assign",
            essays_to_process=[
                EssayToProcess(els_essay_id=essay.id, text_storage_id=f"storage-{essay.id}")
                for essay in essays
            ],
            language="en",
            course_code="ENG5",
            llm_config_overrides=None,
        )

        # Act
        await submit_comparisons_for_async_processing(
            essays_for_api_model=essays,
            cj_batch_id=cj_batch_id,
            session_provider=postgres_session_provider,
            batch_repository=postgres_batch_repository,
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            request_data=request_data,
            llm_interaction=llm_interaction,
            matching_strategy=mock_matching_strategy,
            settings=test_settings,
            correlation_id=uuid.uuid4(),
            log_extra={"test": "header_structure"},
        )

        # Assert: Extract captured requests from mocker
        captured_http_requests = capture_requests_from_mocker(http_mocker)
        assert len(captured_http_requests) > 0

        http_request = captured_http_requests[0]

        # Both prompts should be present
        assert "llm_config_overrides" in http_request
        assert "system_prompt_override" in http_request["llm_config_overrides"]
        assert "user_prompt" in http_request

        system_prompt = http_request["llm_config_overrides"]["system_prompt_override"]
        user_prompt = http_request["user_prompt"]

        # System prompt should define role and constraints
        assert "assessor" in system_prompt.lower() or "judge" in system_prompt.lower()
        assert "constraints:" in system_prompt.lower() or "constraint" in system_prompt.lower()

        # User prompt should contain essay comparison content
        assert "essay" in user_prompt.lower()
        # Should contain the essay IDs
        assert "header-test-essay-1" in user_prompt or "Essay A" in user_prompt
        assert "header-test-essay-2" in user_prompt or "Essay B" in user_prompt

        # Verify no markdown headers in system prompt (should be plain text with labels)
        assert not system_prompt.startswith("#"), "System prompt should not use # headers"

        # User prompt uses **bold** pseudo-headers (not # headers)
        if "**" in user_prompt:
            # If bold headers exist, verify no markdown headers
            assert not any(line.startswith("#") for line in user_prompt.split("\n")), (
                "User prompt should use **bold** not # headers"
            )

        print("\n" + "=" * 80)
        print("SYSTEM PROMPT (in HTTP request):")
        print("=" * 80)
        print(system_prompt)
        print("\n" + "=" * 80)
        print("USER PROMPT (in HTTP request):")
        print("=" * 80)
        print(user_prompt[:500] + "..." if len(user_prompt) > 500 else user_prompt)
        print("=" * 80)


@pytest.fixture
def mock_matching_strategy() -> MagicMock:
    """Provide real optimal graph matching strategy wrapped for protocol compliance."""

    return make_real_matching_strategy_mock()
