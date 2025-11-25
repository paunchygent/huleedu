"""Content hydration for CJ Assessment Service.

This module handles fetching and hydrating content from the Content Service,
including student prompts and judge rubrics for CJ assessment workflows.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.metadata_models import StorageReferenceMetadata
from huleedu_service_libs import Result
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.models_api import PromptHydrationFailure
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment.content_hydration")


def record_prompt_failure(metric: Any, reason: str) -> None:
    """Increment prompt fetch failure metric with defensive guards."""
    if metric is None:
        return
    try:
        metric.labels(reason=reason).inc()
    except Exception:
        try:
            metric.inc()
        except Exception:  # pragma: no cover - defensive guardrail
            logger.debug("Unable to increment CJ prompt failure metric", exc_info=True)


def extract_prompt_storage_id(
    prompt_ref: StorageReferenceMetadata | None,
    *,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    prompt_failure_metric: Any,
) -> str | None:
    """Extract Content Service storage ID for student prompt reference."""
    if prompt_ref is None:
        logger.debug(
            "No student prompt reference provided for CJ batch",
            extra={**log_extra, "correlation_id": str(correlation_id)},
        )
        return None

    references = cast(dict[Any, dict[str, str]], prompt_ref.references or {})
    storage_entry = references.get(ContentType.STUDENT_PROMPT_TEXT)
    if storage_entry is None:
        storage_entry = references.get(ContentType.STUDENT_PROMPT_TEXT.value)  # type: ignore[arg-type]

    if not isinstance(storage_entry, dict):
        logger.warning(
            "Student prompt reference missing expected storage entry for CJ batch",
            extra={
                **log_extra,
                "correlation_id": str(correlation_id),
                "reference_keys": list(references.keys()),
            },
        )
        record_prompt_failure(prompt_failure_metric, "missing_entry")
        return None

    storage_id = storage_entry.get("storage_id")
    if not storage_id:
        logger.warning(
            "Student prompt reference missing storage_id for CJ batch",
            extra={
                **log_extra,
                "correlation_id": str(correlation_id),
                "reference_keys": list(references.keys()),
            },
        )
        record_prompt_failure(prompt_failure_metric, "missing_storage_id")
        return None

    return cast(str, storage_id)


async def hydrate_prompt_text(
    *,
    storage_id: str | None,
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    prompt_failure_metric: Any,
) -> Result[str, PromptHydrationFailure]:
    """Fetch prompt text from Content Service for CJ assessment.

    Returns:
        Result.ok(text) on success
        Result.ok("") if storage_id is None (caller treats as missing prompt)
        Result.err(PromptHydrationFailure) on various failure modes
    """
    if storage_id is None:
        return Result.ok("")

    try:
        prompt_text = await content_client.fetch_content(storage_id, correlation_id)
        if prompt_text:
            logger.debug(
                "Hydrated student prompt text for CJ assessment batch",
                extra={
                    **log_extra,
                    "correlation_id": str(correlation_id),
                    "prompt_storage_id": storage_id,
                    "prompt_preview": prompt_text[:100],
                },
            )
            return Result.ok(prompt_text)

        # Empty content when storage_id exists is an error
        record_prompt_failure(prompt_failure_metric, "empty_content")
        logger.warning(
            "Hydrated student prompt text is empty for CJ assessment batch",
            extra={
                **log_extra,
                "correlation_id": str(correlation_id),
                "prompt_storage_id": storage_id,
            },
        )
        return Result.err(PromptHydrationFailure("empty_content", storage_id))

    except HuleEduError as error:
        record_prompt_failure(prompt_failure_metric, "content_service_error")
        logger.warning(
            "Failed to fetch student prompt text from Content Service for CJ assessment",
            extra={
                **log_extra,
                "correlation_id": str(correlation_id),
                "prompt_storage_id": storage_id,
                "error": getattr(error, "error_detail", str(error)),
            },
        )
        return Result.err(PromptHydrationFailure("content_service_error", storage_id))
    except Exception as error:  # pragma: no cover - defensive guardrail
        record_prompt_failure(prompt_failure_metric, "unexpected_error")
        logger.error(
            "Unexpected error hydrating student prompt text for CJ assessment",
            exc_info=True,
            extra={
                **log_extra,
                "correlation_id": str(correlation_id),
                "prompt_storage_id": storage_id,
                "error": str(error),
            },
        )
        return Result.err(PromptHydrationFailure("unexpected_error", storage_id))


async def hydrate_judge_rubric_context(
    *,
    session_provider: SessionProviderProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    content_client: ContentClientProtocol,
    assignment_id: str | None,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    prompt_failure_metric: Any,
) -> tuple[str | None, str | None]:
    """Fetch judge rubric storage reference and text for the assignment, if available."""

    if not assignment_id:
        return None, None

    try:
        async with session_provider.session() as session:
            instruction = await instruction_repository.get_assessment_instruction(
                session,
                assignment_id=assignment_id,
                course_id=None,
            )
    except Exception:  # pragma: no cover - defensive guard
        logger.error(
            "Failed to load assessment instruction while hydrating judge rubric",
            extra={**log_extra, "assignment_id": assignment_id},
            exc_info=True,
        )
        record_prompt_failure(prompt_failure_metric, "rubric_instruction_lookup_failed")
        return None, None

    if not instruction:
        logger.debug(
            "No assessment instruction found while hydrating judge rubric",
            extra={**log_extra, "assignment_id": assignment_id},
        )
        return None, None

    storage_id = getattr(instruction, "judge_rubric_storage_id", None)
    if not storage_id:
        return None, None

    try:
        rubric_text = await content_client.fetch_content(storage_id, correlation_id)
        if not rubric_text:
            logger.warning(
                "Hydrated judge rubric text is empty",
                extra={**log_extra, "storage_id": storage_id},
            )
            record_prompt_failure(prompt_failure_metric, "rubric_empty_content")
            return storage_id, None

        logger.debug(
            "Hydrated judge rubric text for CJ assessment batch",
            extra={
                **log_extra,
                "storage_id": storage_id,
                "rubric_preview": rubric_text[:100],
            },
        )
        return storage_id, rubric_text

    except HuleEduError as error:
        logger.warning(
            "Failed to fetch judge rubric text from Content Service",
            extra={
                **log_extra,
                "storage_id": storage_id,
                "error": getattr(error, "error_detail", str(error)),
            },
        )
        record_prompt_failure(prompt_failure_metric, "rubric_content_service_error")
        return storage_id, None
    except Exception:  # pragma: no cover - defensive guard
        logger.error(
            "Unexpected error fetching judge rubric text",
            extra={**log_extra, "storage_id": storage_id},
            exc_info=True,
        )
        record_prompt_failure(prompt_failure_metric, "rubric_unexpected_error")
        return storage_id, None
