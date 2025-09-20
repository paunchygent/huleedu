"""Spellcheck result handler for Essay Lifecycle Service.

Handles:
- `SpellcheckResultDataV1` (legacy rich result used for state transitions)
- `SpellcheckResultV1` (new rich result carrying aggregated metrics)
- `SpellcheckPhaseCompletedV1` (thin event for state machine updates)
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.events.spellcheck_models import (
    SpellcheckMetricsV1,
    SpellcheckResultDataV1,
    SpellcheckResultV1,
)
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import get_current_trace_id, trace_operation
from opentelemetry import trace
from quart import current_app, has_app_context

# Import event constants from state machine to ensure consistency
from services.essay_lifecycle_service.constants import MetadataKey
from services.essay_lifecycle_service.essay_state_machine import (
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
    )

logger = create_service_logger("spellcheck_result_handler")


class SpellcheckResultHandler:
    """Handler for spellcheck-related events."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle legacy rich spellcheck result emitted alongside thin event."""

        try:
            is_success = result_data.status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck result",
                extra={
                    "essay_id": result_data.entity_id,
                    "status": result_data.status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            if not result_data.entity_id:
                logger.error("Missing entity_id in spellcheck result")
                return False

            async with self.session_factory() as session:
                async with session.begin():
                    essay_state = await self.repository.get_essay_state(
                        result_data.entity_id, session
                    )
                    if essay_state is None:
                        logger.error(
                            "Essay not found for spellcheck result",
                            extra={
                                "essay_id": result_data.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        return False

                    state_machine = EssayStateMachine(
                        essay_id=result_data.entity_id,
                        initial_status=essay_state.current_status,
                    )

                    trigger = EVT_SPELLCHECK_SUCCEEDED if is_success else EVT_SPELLCHECK_FAILED
                    transition_logged = logger.info if is_success else logger.warning
                    transition_logged(
                        "Spellcheck %s, transitioning state",
                        "succeeded" if is_success else "failed",
                        extra={
                            "essay_id": result_data.entity_id,
                            "current_status": essay_state.current_status.value,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    if not state_machine.trigger_event(trigger):
                        logger.error(
                            "State machine trigger '%s' failed for essay %s from status %s.",
                            trigger,
                            result_data.entity_id,
                            essay_state.current_status.value,
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

                    storage_ref_to_add = None
                    if is_success and result_data.storage_metadata:
                        spellchecked_ref = result_data.storage_metadata.references.get(
                            ContentType.CORRECTED_TEXT
                        )
                        if spellchecked_ref:
                            storage_id = spellchecked_ref.get("default")
                            if storage_id:
                                storage_ref_to_add = (ContentType.CORRECTED_TEXT, storage_id)
                                logger.info(
                                    "Extracted storage reference",
                                    extra={
                                        "storage_id": storage_id,
                                        "content_type": ContentType.CORRECTED_TEXT.value,
                                        "trace_id": get_current_trace_id(),
                                    },
                                )

                    spellcheck_metadata: dict[str, Any] = {
                        "success": is_success,
                        "status": result_data.status.value,
                        "original_text_storage_id": result_data.original_text_storage_id,
                        "storage_metadata": result_data.storage_metadata.model_dump()
                        if result_data.storage_metadata
                        else None,
                        "corrections_made": result_data.corrections_made,
                        "error_info": result_data.system_metadata.error_info
                        if result_data.system_metadata
                        else None,
                    }

                    metrics = getattr(result_data, "correction_metrics", None)
                    if metrics is not None:
                        spellcheck_metadata["metrics"] = metrics.model_dump()

                    metadata_update = {
                        "spellcheck_result": spellcheck_metadata,
                        "current_phase": "spellcheck",
                        "phase_outcome_status": result_data.status.value,
                    }

                    await self.repository.update_essay_status_via_machine(
                        result_data.entity_id,
                        state_machine.current_status,
                        metadata_update,
                        session,
                        storage_reference=storage_ref_to_add,
                        correlation_id=correlation_id,
                    )

                    logger.info(
                        "Successfully updated essay status via state machine",
                        extra={
                            "essay_id": result_data.entity_id,
                            "new_status": state_machine.current_status.value,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    updated_essay_state = await self.repository.get_essay_state(
                        result_data.entity_id, session
                    )
                    if updated_essay_state:
                        await self.batch_coordinator.check_batch_completion(
                            essay_state=updated_essay_state,
                            phase_name=PhaseName.SPELLCHECK,
                            correlation_id=correlation_id,
                            session=session,
                        )

            if confirm_idempotency is not None:
                await confirm_idempotency()

            logger.info(
                "Successfully processed spellcheck result",
                extra={
                    "essay_id": result_data.entity_id,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck result",
                extra={
                    "essay_id": getattr(result_data, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_spellcheck_rich_result(
        self,
        rich_result: SpellcheckResultV1,
        correlation_id: UUID,
    ) -> bool:
        """Persist spellcheck metrics from the SpellcheckResultV1 event."""

        try:
            metrics: SpellcheckMetricsV1 = rich_result.correction_metrics

            async with self.session_factory() as session:
                async with session.begin():
                    essay_state = await self.repository.get_essay_state(
                        rich_result.entity_id, session
                    )
                    if essay_state is None:
                        logger.error(
                            "Essay not found for rich spellcheck result",
                            extra={
                                "essay_id": rich_result.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        return False

                    spellcheck_metadata = dict(
                        essay_state.processing_metadata.get("spellcheck_result", {})
                    )
                    spellcheck_metadata.setdefault(
                        "success",
                        rich_result.status == EssayStatus.SPELLCHECKED_SUCCESS,
                    )
                    spellcheck_metadata.setdefault("status", rich_result.status.value)
                    spellcheck_metadata["corrections_made"] = rich_result.corrections_made
                    spellcheck_metadata["metrics"] = metrics.model_dump()

                    if rich_result.corrected_text_storage_id:
                        spellcheck_metadata.setdefault(
                            "corrected_text_storage_id",
                            rich_result.corrected_text_storage_id,
                        )

                    metadata_updates = {"spellcheck_result": spellcheck_metadata}

                    await self.repository.update_essay_processing_metadata(
                        essay_id=rich_result.entity_id,
                        metadata_updates=metadata_updates,
                        correlation_id=correlation_id,
                        session=session,
                    )

            logger.info(
                "Stored spellcheck metrics from rich event",
                extra={
                    "essay_id": rich_result.entity_id,
                    "batch_id": rich_result.batch_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Error storing spellcheck metrics",
                extra={
                    "essay_id": getattr(rich_result, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_spellcheck_phase_completed(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus,
        corrected_text_storage_id: str | None,
        error_code: str | None,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle thin spellcheck phase completion event."""

        try:
            is_success = status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck phase completed (thin event)",
                extra={
                    "essay_id": essay_id,
                    "batch_id": batch_id,
                    "status": status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            async with self.session_factory() as session:
                async with session.begin():
                    essay_state = await self.repository.get_essay_state(essay_id, session)
                    if essay_state is None:
                        logger.error(
                            "Essay not found for spellcheck phase completed",
                            extra={
                                "essay_id": essay_id,
                                "batch_id": batch_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        return False

                    state_machine = EssayStateMachine(
                        essay_id=essay_id,
                        initial_status=essay_state.current_status,
                    )

                    trigger = EVT_SPELLCHECK_SUCCEEDED if is_success else EVT_SPELLCHECK_FAILED
                    if not state_machine.trigger_event(trigger):
                        logger.error(
                            "State machine trigger '%s' failed for essay %s from status %s.",
                            trigger,
                            essay_id,
                            essay_state.current_status.value,
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

                    storage_ref_to_add = None
                    if is_success and corrected_text_storage_id:
                        storage_ref_to_add = (
                            ContentType.CORRECTED_TEXT,
                            corrected_text_storage_id,
                        )
                        logger.info(
                            "Using corrected text storage reference",
                            extra={
                                "storage_id": corrected_text_storage_id,
                                "content_type": ContentType.CORRECTED_TEXT.value,
                            },
                        )

                    commanded_phases = essay_state.processing_metadata.get(
                        MetadataKey.COMMANDED_PHASES, []
                    )
                    if "spellcheck" not in commanded_phases:
                        commanded_phases.append("spellcheck")

                    metadata_update: dict[str, Any] = {
                        "spellcheck_result": {
                            "success": is_success,
                            "status": status.value,
                            "corrected_text_storage_id": corrected_text_storage_id,
                            "error_code": error_code,
                        },
                        "current_phase": "spellcheck",
                        "commanded_phases": commanded_phases,
                        "phase_outcome_status": status.value,
                    }

                    if is_success:
                        stored_metrics = (
                            essay_state.processing_metadata.get("spellcheck_result", {})
                        ).get("metrics")
                        if stored_metrics:
                            metadata_update["spellcheck_result"]["metrics"] = stored_metrics

                    await self.repository.update_essay_status_via_machine(
                        essay_id,
                        state_machine.current_status,
                        metadata_update,
                        session,
                        storage_reference=storage_ref_to_add,
                        correlation_id=correlation_id,
                    )

                    logger.info(
                        "Successfully updated essay status via state machine (thin event)",
                        extra={
                            "essay_id": essay_id,
                            "new_status": state_machine.current_status.value,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    updated_essay_state = await self.repository.get_essay_state(essay_id, session)
                    if updated_essay_state:
                        await self.batch_coordinator.check_batch_completion(
                            essay_state=updated_essay_state,
                            phase_name=PhaseName.SPELLCHECK,
                            correlation_id=correlation_id,
                            session=session,
                        )

            if confirm_idempotency is not None:
                await confirm_idempotency()

            logger.info(
                "Successfully processed spellcheck phase completed (thin event)",
                extra={
                    "essay_id": essay_id,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck phase completed",
                extra={
                    "essay_id": essay_id,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
