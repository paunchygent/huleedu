"""Unit tests for :pyclass:`DefaultPipelineRules`.

These tests verify dependency ordering, pruning, and prerequisite validation
using mocked dependencies to isolate rules logic.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.batch_conductor_service.implementations.pipeline_rules_impl import (
    DefaultPipelineRules,
)


@pytest.fixture
def pipeline_definition():
    """Simple two-step pipeline: spellcheck -> ai_feedback."""

    from services.batch_conductor_service.pipeline_definitions import (
        PipelineDefinition,
        PipelineStep,
    )

    return PipelineDefinition(
        description="simple",
        steps=[
            PipelineStep(
                name="spellcheck",
                service_name="svc_spellcheck",
                event_type="evt.spell",
                event_data_model="M",
            ),
            PipelineStep(
                name="ai_feedback",
                service_name="svc_ai",
                event_type="evt.ai",
                event_data_model="M",
                depends_on=["spellcheck"],
            ),
        ],
    )


@pytest.fixture
def mock_pipeline_generator(pipeline_definition):
    """Mock PipelineGenerator for boundary testing."""
    mock = AsyncMock()
    mock.list_available_pipelines.return_value = ["default"]
    mock.get_pipeline_definition.return_value = pipeline_definition
    return mock


@pytest.fixture
def mock_batch_state_repository():
    """Mock BatchStateRepository for boundary testing."""
    mock = AsyncMock()
    mock.is_batch_step_complete.return_value = False
    return mock


@pytest.fixture
def pipeline_rules(mock_pipeline_generator, mock_batch_state_repository):
    """Create DefaultPipelineRules with mocked dependencies."""
    return DefaultPipelineRules(
        pipeline_generator=mock_pipeline_generator,
        batch_state_repository=mock_batch_state_repository,
    )


@pytest.mark.asyncio
async def test_resolve_pipeline_dependencies_basic(pipeline_rules):
    """Test basic pipeline dependency resolution."""

    result = await pipeline_rules.resolve_pipeline_dependencies("ai_feedback")

    assert result == ["spellcheck", "ai_feedback"]


@pytest.mark.asyncio
async def test_resolve_pipeline_dependencies_with_batch_id(pipeline_rules, mock_batch_state_repository):
    """Test pipeline dependency resolution with batch context."""

    # Mark spellcheck as already done for this batch
    async def _is_complete(batch_id: str, step: str):
        return step == "spellcheck"

    mock_batch_state_repository.is_batch_step_complete.side_effect = _is_complete

    result = await pipeline_rules.resolve_pipeline_dependencies(
        "ai_feedback", batch_id="batch-123"
    )

    assert result == ["ai_feedback"]


@pytest.mark.asyncio
async def test_validate_pipeline_prerequisites(pipeline_rules, mock_batch_state_repository):
    """Test pipeline prerequisite validation."""

    # Test prerequisite validation
    # If spellcheck incomplete → prerequisites not met
    mock_batch_state_repository.is_batch_step_complete.return_value = False
    ok = await pipeline_rules.validate_pipeline_prerequisites("ai_feedback", "batch-1")
    assert ok is False

    # Now mark spellcheck complete
    async def _complete(_, step):
        return step == "spellcheck"

    mock_batch_state_repository.is_batch_step_complete.side_effect = _complete
    ok = await pipeline_rules.validate_pipeline_prerequisites("ai_feedback", "batch-1")
    assert ok is True


@pytest.mark.asyncio
async def test_prune_completed_steps_none_complete(
    pipeline_rules, mock_batch_state_repository
):
    """Test pruning when no steps are complete."""

    # Mock all steps as incomplete
    mock_batch_state_repository.is_batch_step_complete.return_value = False

    pipeline_steps = ["spellcheck", "ai_feedback", "cj_assessment"]
    result = await pipeline_rules.prune_completed_steps(
        pipeline_steps, batch_id="batch-123"
    )

    # All steps should remain since none are complete
    assert result == ["spellcheck", "ai_feedback", "cj_assessment"]


@pytest.mark.asyncio
async def test_prune_completed_steps_some_complete(
    pipeline_rules, mock_batch_state_repository
):
    """Test pruning when some steps are complete."""

    # Mock spellcheck as complete, others as incomplete
    def mock_completion_status(batch_id: str, step_name: str) -> bool:
        return step_name == "spellcheck"

    mock_batch_state_repository.is_batch_step_complete.side_effect = mock_completion_status

    pipeline_steps = ["spellcheck", "ai_feedback", "cj_assessment"]
    result = await pipeline_rules.prune_completed_steps(
        pipeline_steps, batch_id="batch-123"
    )

    # Only incomplete steps should remain
    assert result == ["ai_feedback", "cj_assessment"]


@pytest.mark.asyncio
async def test_prune_completed_steps_all_complete(
    pipeline_rules, mock_batch_state_repository
):
    """Test pruning when all steps are complete."""

    # Mock all steps as complete
    mock_batch_state_repository.is_batch_step_complete.return_value = True

    pipeline_steps = ["spellcheck", "ai_feedback"]
    result = await pipeline_rules.prune_completed_steps(
        pipeline_steps, batch_id="batch-123"
    )

    # No steps should remain since all are complete
    assert result == []


@pytest.mark.asyncio
async def test_prune_completed_steps_empty_pipeline(
    pipeline_rules, mock_batch_state_repository
):
    """Test pruning with empty pipeline."""

    result = await pipeline_rules.prune_completed_steps([], batch_id="batch-123")

    # Empty list should remain empty
    assert result == []

    # BatchStateRepository should not be called for empty pipeline
    mock_batch_state_repository.is_batch_step_complete.assert_not_called()
