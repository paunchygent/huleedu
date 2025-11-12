"""Batch preparation phase for CJ Assessment workflow.

This module handles the initial setup and content preparation phases
of the CJ assessment workflow.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import CJProcessingMetadata, EssayForComparison
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    ContentClientProtocol,
)

logger = create_service_logger("cj_assessment_service.batch_preparation")


async def create_cj_batch(
    request_data: dict[str, Any],
    correlation_id: UUID,
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
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
        # Prepare shared metrics instances once per batch creation
        business_metrics = get_business_metrics()
        prompt_success_metric = business_metrics.get("prompt_fetch_success")
        prompt_failure_metric = business_metrics.get("prompt_fetch_failures")

        # Extract data from request
        bos_batch_id = request_data.get("bos_batch_id")
        language = request_data.get("language", "en")
        course_code = request_data.get("course_code", "")
        essays_to_process = request_data.get("essays_to_process", [])
        assignment_id = request_data.get("assignment_id")  # For anchor essay lookup
        prompt_storage_id = request_data.get("student_prompt_storage_id")
        prompt_text = request_data.get("student_prompt_text")
        # Identity fields for credit attribution (Phase 3: Entitlements integration)
        user_id = request_data.get("user_id")
        org_id = request_data.get("org_id")

        if not bos_batch_id or not essays_to_process:
            raise ValueError("Missing required fields: bos_batch_id or essays_to_process")

        # Create CJ batch record
        cj_batch = await database.create_new_cj_batch(
            session=session,
            bos_batch_id=bos_batch_id,
            event_correlation_id=str(correlation_id),
            language=language,
            course_code=course_code,
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=len(essays_to_process),
            user_id=user_id,
            org_id=org_id,
        )

        # Auto-hydrate student prompt from assignment instruction
        if assignment_id and not prompt_storage_id:
            instruction = await database.get_assessment_instruction(
                session, assignment_id=assignment_id, course_id=None
            )
            if instruction and instruction.student_prompt_storage_id:
                prompt_storage_id = instruction.student_prompt_storage_id
                logger.info(
                    "Auto-hydrated student prompt from instruction",
                    extra={
                        **log_extra,
                        "assignment_id": assignment_id,
                        "storage_id": prompt_storage_id,
                    },
                )

        # Hydration fallback if storage_id exists but text is missing
        if prompt_storage_id and not prompt_text:
            try:
                prompt_text = await content_client.fetch_content(prompt_storage_id, correlation_id)
                logger.info(
                    "Hydrated prompt text via fallback in batch creation",
                    extra={**log_extra, "storage_id": prompt_storage_id},
                )
                if prompt_text and prompt_success_metric:
                    try:
                        prompt_success_metric.inc()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug(
                            "Unable to increment prompt success metric in batch creation",
                            exc_info=True,
                        )
            except Exception as e:
                logger.error(
                    f"Failed to hydrate prompt in batch creation: {e}",
                    extra={**log_extra, "storage_id": prompt_storage_id},
                )
                if prompt_failure_metric:
                    try:
                        prompt_failure_metric.labels(reason="batch_creation_hydration_failed").inc()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug(
                            "Unable to increment prompt failure metric in batch creation",
                            exc_info=True,
                        )

        # Use typed metadata with permissive merge
        if prompt_storage_id or prompt_text:
            existing = cj_batch.processing_metadata or {}
            typed = CJProcessingMetadata(
                student_prompt_storage_id=prompt_storage_id,
                student_prompt_text=prompt_text,
            ).model_dump(exclude_none=True)
            cj_batch.processing_metadata = {**existing, **typed}
            await session.flush()

        # Store assignment_id if provided
        if assignment_id:
            cj_batch.assignment_id = assignment_id
            await session.flush()
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
                content = await content_client.fetch_content(text_storage_id, correlation_id)

                assessment_input_text = content

                # Store essay for CJ processing (mark as student essay)
                cj_processed_essay = await database.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=els_essay_id,
                    text_storage_id=text_storage_id,
                    assessment_input_text=assessment_input_text,
                    processing_metadata={"is_anchor": False},  # Mark as student essay
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

        # Add anchor essays if assignment_id present
        cj_batch = await database.get_cj_batch_upload(session, cj_batch_id)
        if cj_batch and cj_batch.assignment_id:
            anchors = await _fetch_and_add_anchors(
                session, cj_batch, content_client, database, correlation_id
            )
            essays_for_api_model.extend(anchors)

        logger.info(
            f"Prepared {len(essays_for_api_model)} essays for CJ assessment",
            extra=log_extra,
        )

        return essays_for_api_model


async def _fetch_and_add_anchors(
    session: AsyncSession,
    batch_upload: CJBatchUpload,
    content_client: ContentClientProtocol,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
) -> list[EssayForComparison]:
    """Fetch anchor essays and add to comparison pool."""
    anchors: list[EssayForComparison] = []

    # Ensure assignment_id is not None (checked by caller)
    if not batch_upload.assignment_id:
        return anchors

    # Resolve assignment metadata to determine active grade scale
    assignment_context = await database.get_assignment_context(
        session=session,
        assignment_id=batch_upload.assignment_id,
    )

    if not assignment_context:
        logger.warning(
            "No assignment context found while attempting to add anchors",
            extra={
                "correlation_id": correlation_id,
                "assignment_id": batch_upload.assignment_id,
            },
        )
        return anchors

    grade_scale = assignment_context.get("grade_scale", "swedish_8_anchor")

    # Get anchor references for this assignment
    anchor_refs = await database.get_anchor_essay_references(
        session,
        batch_upload.assignment_id,
        grade_scale=grade_scale,
    )

    for ref in anchor_refs:
        try:
            # Generate synthetic ID
            synthetic_id = f"ANCHOR_{ref.id}_{uuid4().hex[:8]}"

            # Fetch content using renamed field
            content = await content_client.fetch_content(ref.text_storage_id, correlation_id)

            # Store with metadata
            await database.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch_upload.id,
                els_essay_id=synthetic_id,
                text_storage_id=ref.text_storage_id,
                assessment_input_text=content,
                processing_metadata={
                    "is_anchor": True,
                    "known_grade": ref.grade,
                    "anchor_ref_id": str(ref.id),
                },
            )

            # Ensure anchor is persisted before creating comparisons
            await session.flush()

            # Create API model
            anchor_for_api = EssayForComparison(
                id=synthetic_id,
                text_content=content,
                current_bt_score=0.0,
            )
            anchors.append(anchor_for_api)

        except Exception as e:
            logger.error(
                f"Failed to fetch anchor essay {ref.id}: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "anchor_id": ref.id,
                    "exception_type": type(e).__name__,
                },
                exc_info=True,
            )
            # Continue with other anchors

    logger.info(f"Added {len(anchors)} anchor essays to batch {batch_upload.id}")
    return anchors
