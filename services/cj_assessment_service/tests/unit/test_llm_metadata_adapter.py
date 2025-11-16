"""Tests for the CJLLMComparisonMetadata adapter."""

from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)


def _build_task(essay_a_id: str = "essay-a", essay_b_id: str = "essay-b") -> ComparisonTask:
    """Create a reusable comparison task for metadata tests."""
    return ComparisonTask(
        essay_a=EssayForComparison(id=essay_a_id, text_content="essay A"),
        essay_b=EssayForComparison(id=essay_b_id, text_content="essay B"),
        prompt="Compare essay A and essay B",
    )


class TestCJLLMComparisonMetadata:
    """Behavioural tests for the typed metadata adapter."""

    def test_from_comparison_task_sets_required_fields(self) -> None:
        """Ensure builder captures essay identifiers every time."""
        task = _build_task()
        metadata = CJLLMComparisonMetadata.from_comparison_task(task)

        serialized = metadata.to_request_metadata()
        assert serialized == {
            "essay_a_id": "essay-a",
            "essay_b_id": "essay-b",
        }

    def test_optional_fields_emit_only_when_set(self) -> None:
        """Bos batch ids and future hints stay additive/optional."""
        task = _build_task()
        metadata = CJLLMComparisonMetadata.from_comparison_task(task, bos_batch_id="bos-123")
        metadata = metadata.with_additional_context(
            cj_llm_batching_mode="per_request",
            comparison_iteration=0,
        )

        serialized = metadata.to_request_metadata()
        assert serialized["bos_batch_id"] == "bos-123"
        assert serialized["cj_llm_batching_mode"] == "per_request"
        assert serialized["comparison_iteration"] == 0

    def test_additional_context_does_not_drop_known_fields(self) -> None:
        """Unknown keys remain additive while core ids stay intact."""
        task = _build_task("essay-x", "essay-y")
        metadata = CJLLMComparisonMetadata.from_comparison_task(task)
        enriched = metadata.with_additional_context(experiment_tag="eng5-nov-2025")

        serialized = enriched.to_request_metadata()
        assert serialized["essay_a_id"] == "essay-x"
        assert serialized["essay_b_id"] == "essay-y"
        assert serialized["experiment_tag"] == "eng5-nov-2025"
