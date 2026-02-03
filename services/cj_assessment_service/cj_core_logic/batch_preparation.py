"""Batch preparation phase for CJ Assessment workflow.

This module handles the initial setup and content preparation phases
of the CJ assessment workflow.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
    merge_batch_upload_metadata,
    merge_essay_processing_metadata,
)
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import (
    CJAnchorMetadata,
    CJAssessmentRequestData,
    CJEessayMetadata,
    CJProcessingMetadata,
    EssayForComparison,
    OriginalCJRequestMetadata,
)
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJEssayRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.batch_preparation")

_CANONICAL_NATIONAL_CONTEXT_ORIGIN = "canonical_national"


async def create_cj_batch(
    request_data: CJAssessmentRequestData,
    correlation_id: UUID,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    content_client: ContentClientProtocol,
    log_extra: dict[str, Any],
) -> int:
    """Create a new CJ batch record and return its ID.

    Args:
        request_data: The CJ assessment request data from ELS
        correlation_id: Optional correlation ID for event tracing
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch operations
        instruction_repository: Instruction repository for assessment instructions
        content_client: Content client protocol implementation
        log_extra: Logging context data

    Returns:
        The created CJ batch ID

    Raises:
        ValueError: If required fields are missing
    """
    # Prepare shared metrics instances once per batch creation
    business_metrics = get_business_metrics()
    prompt_success_metric = business_metrics.get("prompt_fetch_success")
    prompt_failure_metric = business_metrics.get("prompt_fetch_failures")

    # Extract data from request
    bos_batch_id = request_data.bos_batch_id
    language = request_data.language
    course_code = request_data.course_code
    essays_to_process = request_data.essays_to_process
    assignment_id = request_data.assignment_id  # For anchor essay lookup
    prompt_storage_id = request_data.student_prompt_storage_id
    prompt_text = request_data.student_prompt_text
    judge_rubric_storage_id = request_data.judge_rubric_storage_id
    judge_rubric_text = request_data.judge_rubric_text
    # Identity fields for credit attribution (Phase 3: Entitlements integration)
    user_id = request_data.user_id
    org_id = request_data.org_id

    if not bos_batch_id or not essays_to_process:
        raise ValueError("Missing required fields: bos_batch_id or essays_to_process")

    # These payloads are computed inside the session block but applied after commit
    instruction = None
    typed_metadata: dict[str, Any] | None = None
    original_request_payload: dict[str, Any] | None = None

    async with session_provider.session() as session:
        # Create CJ batch record
        cj_batch = await batch_repository.create_new_cj_batch(
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

        if assignment_id:
            instruction = await instruction_repository.get_assessment_instruction(
                session, assignment_id=assignment_id, course_id=None
            )
            if instruction is None:
                raise ValueError(
                    f"Unknown assignment_id '{assignment_id}': missing assessment_instructions"
                )

            context_origin = instruction.context_origin
            rubric_override = (
                request_data.llm_config_overrides.judge_rubric_override
                if request_data.llm_config_overrides
                else None
            )

            if rubric_override and context_origin == _CANONICAL_NATIONAL_CONTEXT_ORIGIN:
                raise ValueError(
                    "judge_rubric_override is not allowed for canonical assignments. "
                    "Set assessment_instructions.context_origin to a non-canonical value (e.g. "
                    "'research_experiment') before running rubric A/B tests for assignment_id="
                    f"{assignment_id}."
                )

            prompt_storage_id = instruction.student_prompt_storage_id
            prompt_text = None
            judge_rubric_storage_id = instruction.judge_rubric_storage_id
            judge_rubric_text = None

            if rubric_override and context_origin != _CANONICAL_NATIONAL_CONTEXT_ORIGIN:
                judge_rubric_text = rubric_override
                judge_rubric_storage_id = None
                logger.info(
                    "Applied judge_rubric_override for non-canonical assignment",
                    extra={**log_extra, "override_length": len(rubric_override)},
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

        # Hydration fallback for judge rubric text
        if judge_rubric_storage_id and not judge_rubric_text:
            try:
                judge_rubric_text = await content_client.fetch_content(
                    judge_rubric_storage_id, correlation_id
                )
                logger.info(
                    "Hydrated judge rubric text via fallback in batch creation",
                    extra={**log_extra, "storage_id": judge_rubric_storage_id},
                )
            except Exception as e:
                logger.error(
                    f"Failed to hydrate judge rubric in batch creation: {e}",
                    extra={**log_extra, "storage_id": judge_rubric_storage_id},
                )
                if prompt_failure_metric:
                    try:
                        if hasattr(prompt_failure_metric, "labels"):
                            prompt_failure_metric.labels(
                                reason="batch_creation_rubric_hydration_failed"
                            ).inc()
                        else:
                            prompt_failure_metric.inc()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug(
                            "Unable to increment rubric hydration failure metric in batch creation",
                            exc_info=True,
                        )

        # Apply judge_rubric_override for guest runs (assignment_id=None).
        # Assignment-bound override is handled above (context_origin gated).
        if (
            assignment_id is None
            and request_data.llm_config_overrides
            and request_data.llm_config_overrides.judge_rubric_override
        ):
            judge_rubric_text = request_data.llm_config_overrides.judge_rubric_override
            judge_rubric_storage_id = None
            logger.info(
                "Applied judge_rubric_override from llm_config_overrides",
                extra={
                    **log_extra,
                    "override_length": len(judge_rubric_text),
                },
            )

        # Use typed metadata with merge helpers
        typed_metadata = CJProcessingMetadata(
            student_prompt_storage_id=prompt_storage_id,
            student_prompt_text=prompt_text,
            judge_rubric_storage_id=judge_rubric_storage_id,
            judge_rubric_text=judge_rubric_text,
        ).model_dump(exclude_none=True)

        original_request_payload = OriginalCJRequestMetadata(
            assignment_id=assignment_id,
            language=request_data.language,
            course_code=request_data.course_code,
            cj_source=request_data.cj_source,
            cj_request_type=request_data.cj_request_type,
            student_prompt_text=request_data.student_prompt_text,
            student_prompt_storage_id=request_data.student_prompt_storage_id,
            judge_rubric_text=request_data.judge_rubric_text,
            judge_rubric_storage_id=request_data.judge_rubric_storage_id,
            llm_config_overrides=request_data.llm_config_overrides,
            batch_config_overrides=request_data.batch_config_overrides,
            max_comparisons_override=request_data.max_comparisons_override,
            user_id=request_data.user_id,
            org_id=request_data.org_id,
        ).model_dump(exclude_none=True)

        # Store assignment_id if provided
        if assignment_id:
            cj_batch.assignment_id = assignment_id
            await session.flush()

        cj_batch_id: int = cj_batch.id
        await session.commit()

    # Apply metadata updates in separate, short-lived sessions after the batch exists
    metadata_updates: dict[str, Any] = {}
    if typed_metadata:
        metadata_updates.update(typed_metadata)
    if original_request_payload:
        metadata_updates["original_request"] = original_request_payload

    if metadata_updates:
        await merge_batch_upload_metadata(
            session_provider=session_provider,
            cj_batch_id=cj_batch_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

    if original_request_payload:
        await merge_batch_processing_metadata(
            session_provider=session_provider,
            cj_batch_id=cj_batch_id,
            metadata_updates={"original_request": original_request_payload},
            correlation_id=correlation_id,
        )

    logger.info(f"Created internal CJ batch {cj_batch_id}", extra=log_extra)
    return cj_batch_id


async def prepare_essays_for_assessment(
    request_data: CJAssessmentRequestData,
    cj_batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    anchor_repository: AnchorRepositoryProtocol,
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> list[EssayForComparison]:
    """Fetch content and prepare essays for CJ assessment.

    Args:
        request_data: The CJ assessment request data from ELS
        cj_batch_id: The CJ batch ID to associate essays with
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch operations
        essay_repository: Essay repository for essay operations
        instruction_repository: Instruction repository for assessment instructions
        anchor_repository: Anchor repository for anchor essay management
        content_client: Content client protocol implementation
        correlation_id: Request correlation ID for tracing
        log_extra: Logging context data

    Returns:
        List of essays prepared for comparison
    """
    # Collect metadata updates to apply after essays have been persisted
    student_metadata_updates: list[tuple[str, dict[str, Any]]] = []
    anchor_metadata_updates: list[tuple[str, dict[str, Any]]] = []

    async with session_provider.session() as session:
        await batch_repository.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.FETCHING_CONTENT,
        )

        essays_for_api_model: list[EssayForComparison] = []
        essays_to_process = request_data.essays_to_process

        for essay_info in essays_to_process:
            els_essay_id = essay_info.els_essay_id
            text_storage_id = essay_info.text_storage_id

            if not els_essay_id or not text_storage_id:
                logger.warning(f"Skipping essay with missing IDs: {essay_info}")
                continue

            try:
                # Fetch spellchecked content using new correlation_id-aware interface
                content = await content_client.fetch_content(text_storage_id, correlation_id)

                assessment_input_text = content

                # Store essay for CJ processing (mark as student essay)
                cj_processed_essay = await essay_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    els_essay_id=els_essay_id,
                    text_storage_id=text_storage_id,
                    assessment_input_text=assessment_input_text,
                )

                student_metadata = CJEessayMetadata(is_anchor=False).model_dump(exclude_none=True)
                if student_metadata:
                    student_metadata_updates.append((els_essay_id, student_metadata))

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
        cj_batch = await batch_repository.get_cj_batch_upload(session, cj_batch_id)
        if cj_batch and cj_batch.assignment_id:
            anchors = await _fetch_and_add_anchors(
                session_provider,
                session,
                cj_batch,
                content_client,
                instruction_repository,
                anchor_repository,
                essay_repository,
                correlation_id,
                metadata_accumulator=anchor_metadata_updates,
            )
            essays_for_api_model.extend(anchors)

            # Net size (n in nC2) for completion gating should reflect the
            # full CJ graph (students + anchors), not just the original
            # student cohort. Update expected_essay_count so downstream
            # completion_denominator() and related logic see the true CJ
            # node count for this batch.
            cj_batch.expected_essay_count = len(essays_for_api_model)

        # Persist all prepared essays before any cross-session operations use them
        await session.commit()

        logger.info(
            f"Prepared {len(essays_for_api_model)} essays for CJ assessment",
            extra=log_extra,
        )

    # Apply per-essay metadata updates using fresh sessions
    for essay_id, metadata in student_metadata_updates + anchor_metadata_updates:
        await merge_essay_processing_metadata(
            session_provider=session_provider,
            els_essay_id=essay_id,
            metadata_updates=metadata,
            correlation_id=correlation_id,
        )

    return essays_for_api_model


async def _fetch_and_add_anchors(
    session_provider: SessionProviderProtocol,
    session: AsyncSession,
    batch_upload: CJBatchUpload,
    content_client: ContentClientProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    anchor_repository: AnchorRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    correlation_id: UUID,
    metadata_accumulator: list[tuple[str, dict[str, Any]]] | None = None,
) -> list[EssayForComparison]:
    """Fetch anchor essays and add to comparison pool.

    Args:
        session_provider: Session provider for metadata merge helpers
        session: Active database session
        batch_upload: The batch upload record
        content_client: Content client protocol implementation
        instruction_repository: Instruction repository for assessment instructions
        anchor_repository: Anchor repository for anchor essay management
        essay_repository: Essay repository for essay operations
        correlation_id: Request correlation ID for tracing

    Returns:
        List of anchor essays prepared for comparison
    """
    anchors: list[EssayForComparison] = []

    # Ensure assignment_id is not None (checked by caller)
    if not batch_upload.assignment_id:
        return anchors

    # Resolve assignment metadata to determine active grade scale
    assignment_context = await instruction_repository.get_assignment_context(
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
    anchor_refs = await anchor_repository.get_anchor_essay_references(
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
            await essay_repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch_upload.id,
                els_essay_id=synthetic_id,
                text_storage_id=ref.text_storage_id,
                assessment_input_text=content,
                processing_metadata={"is_anchor": True},
            )

            # Ensure anchor is persisted before creating comparisons
            await session.flush()

            anchor_meta = CJAnchorMetadata(
                known_grade=ref.grade,
                anchor_ref_id=str(ref.id) if getattr(ref, "id", None) is not None else None,
                text_storage_id=ref.text_storage_id,
                anchor_label=getattr(ref, "anchor_label", None),
            ).model_dump(exclude_none=True)

            if anchor_meta:
                if metadata_accumulator is not None:
                    metadata_accumulator.append((synthetic_id, anchor_meta))
                else:
                    await merge_essay_processing_metadata(
                        session_provider=session_provider,
                        els_essay_id=synthetic_id,
                        metadata_updates=anchor_meta,
                        correlation_id=correlation_id,
                    )

            # Create API model
            anchor_for_api = EssayForComparison(
                id=synthetic_id,
                text_content=content,
                current_bt_score=0.0,
                is_anchor=True,
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
