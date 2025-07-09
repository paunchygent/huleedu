"""Batch preparation phase for CJ Assessment workflow.

This module handles the initial setup and content preparation phases
of the CJ assessment workflow.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    ContentClientProtocol,
)

logger = create_service_logger("cj_assessment_service.batch_preparation")


async def create_cj_batch(
    request_data: dict[str, Any],
    correlation_id: str,
    database: CJRepositoryProtocol,
    log_extra: dict[str, Any],
) -> int:
    """Create a new CJ batch record and return its ID.

    Args:
        request_data: The CJ assessment request data from ELS
        correlation_id: Optional correlation ID for event tracing
        database: Database access protocol implementation
        log_extra: Logging context data

    Returns:
        The created CJ batch ID

    Raises:
        ValueError: If required fields are missing
    """
    async with database.session() as session:
        # Extract data from request
        bos_batch_id = request_data.get("bos_batch_id")
        language = request_data.get("language", "en")
        course_code = request_data.get("course_code", "")
        essay_instructions = request_data.get("essay_instructions", "")
        essays_to_process = request_data.get("essays_to_process", [])

        if not bos_batch_id or not essays_to_process:
            raise ValueError("Missing required fields: bos_batch_id or essays_to_process")

        # Create CJ batch record
        cj_batch = await database.create_new_cj_batch(
            session=session,
            bos_batch_id=bos_batch_id,
            event_correlation_id=correlation_id,
            language=language,
            course_code=course_code,
            essay_instructions=essay_instructions,
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=len(essays_to_process),
        )
        cj_batch_id: int = cj_batch.id

        logger.info(f"Created internal CJ batch {cj_batch_id}", extra=log_extra)
        return cj_batch_id


async def prepare_essays_for_assessment(
    request_data: dict[str, Any],
    cj_batch_id: int,
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> list[EssayForComparison]:
    """Fetch content and prepare essays for CJ assessment.

    Args:
        request_data: The CJ assessment request data from ELS
        cj_batch_id: The CJ batch ID to associate essays with
        database: Database access protocol implementation
        content_client: Content client protocol implementation
        correlation_id: Request correlation ID for tracing
        log_extra: Logging context data

    Returns:
        List of essays prepared for comparison
    """
    async with database.session() as session:
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.FETCHING_CONTENT,
        )

        essays_for_api_model: list[EssayForComparison] = []
        essays_to_process = request_data.get("essays_to_process", [])

        for essay_info in essays_to_process:
            els_essay_id = essay_info.get("els_essay_id")
            text_storage_id = essay_info.get("text_storage_id")

            if not els_essay_id or not text_storage_id:
                logger.warning(f"Skipping essay with missing IDs: {essay_info}")
                continue

            try:
                # Fetch spellchecked content using new correlation_id-aware interface
                content, content_error = await content_client.fetch_content(
                    text_storage_id, correlation_id
                )

                if content_error:
                    logger.error(
                        f"Failed to fetch content for essay {els_essay_id}: {content_error.message}",
                        extra={
                            "correlation_id": correlation_id,
                            "els_essay_id": els_essay_id,
                            "text_storage_id": text_storage_id,
                            "error_code": content_error.error_code.value,
                        },
                    )
                    continue  # Skip this essay and continue with others

                if content is None:
                    logger.error(
                        f"Content is None for essay {els_essay_id} despite no error",
                        extra={
                            "correlation_id": correlation_id,
                            "els_essay_id": els_essay_id,
                            "text_storage_id": text_storage_id,
                        },
                    )
                    continue  # Skip this essay and continue with others

                assessment_input_text = content

                # Store essay for CJ processing
                cj_processed_essay = await database.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=els_essay_id,
                    text_storage_id=text_storage_id,
                    assessment_input_text=assessment_input_text,
                )

                # Create EssayForComparison for the comparison loop
                essay_for_api = EssayForComparison(
                    id=els_essay_id,  # string ELS essay ID
                    text_content=assessment_input_text,
                    current_bt_score=cj_processed_essay.current_bt_score or 0.0,
                )
                essays_for_api_model.append(essay_for_api)

                logger.debug(
                    f"Prepared essay {els_essay_id} for CJ assessment",
                    extra={
                        "correlation_id": correlation_id,
                        "els_essay_id": els_essay_id,
                        "cj_batch_id": cj_batch_id,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed to prepare essay {els_essay_id}: {e}",
                    extra={
                        "correlation_id": correlation_id,
                        "els_essay_id": els_essay_id,
                        "cj_batch_id": cj_batch_id,
                        "exception_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                # Continue with other essays rather than failing entire batch

        logger.info(
            f"Prepared {len(essays_for_api_model)} essays for CJ assessment",
            extra=log_extra,
        )

        return essays_for_api_model
