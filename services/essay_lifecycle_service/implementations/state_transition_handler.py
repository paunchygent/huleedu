"""
State transition handler for Essay Lifecycle Service.

Provides common state machine operations used by all result handlers,
following SRP and DDD patterns for centralized state management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger

# Import at runtime to avoid circular imports
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from services.essay_lifecycle_service.essay_state_machine import EssayStateMachine
    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
    )

# Import EssayStateMachine at runtime since it's used in the code
from services.essay_lifecycle_service.essay_state_machine import EssayStateMachine

logger = create_service_logger("state_transition_handler")


class StateTransitionHandler:
    """Handles common state machine operations for essay state transitions."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

    async def transition_essay_state(
        self,
        essay_id: str,
        trigger_event: str,
        phase_name: str,
        success: bool,
        result_metadata: dict[str, Any],
        session: AsyncSession,
        correlation_id: UUID,
        storage_reference: tuple[ContentType, str] | None = None,
    ) -> bool:
        """
        Perform state transition for an essay using EssayStateMachine.

        Args:
            essay_id: Essay identifier
            trigger_event: State machine event to trigger
            phase_name: Current processing phase
            success: Whether the operation was successful
            result_metadata: Result-specific metadata to store
            session: Database session
            correlation_id: Correlation ID for tracking
            storage_reference: Optional storage reference to add

        Returns:
            True if state transition succeeded, False otherwise
        """
        try:
            # Get current essay state
            essay_state = await self.repository.get_essay_state(essay_id, session)
            if essay_state is None:
                logger.error(
                    f"Essay not found for {phase_name} state transition",
                    extra={
                        "essay_id": essay_id,
                        "phase": phase_name,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            # Create state machine and trigger event
            state_machine = EssayStateMachine(
                essay_id=essay_id, initial_status=essay_state.current_status
            )

            # Attempt state transition
            if state_machine.trigger_event(trigger_event):
                # Build metadata with preserved commanded_phases
                metadata = self._build_essay_metadata(
                    essay_state, phase_name, success, result_metadata
                )

                await self.repository.update_essay_status_via_machine(
                    essay_id,
                    state_machine.current_status,
                    metadata,
                    session,
                    storage_reference=storage_reference,
                    correlation_id=correlation_id,
                )

                logger.info(
                    f"Successfully updated essay status via state machine for {phase_name}",
                    extra={
                        "essay_id": essay_id,
                        "new_status": state_machine.current_status.value,
                        "phase": phase_name,
                        "correlation_id": str(correlation_id),
                    },
                )
                return True
            else:
                logger.error(
                    f"State machine trigger '{trigger_event}' failed for essay "
                    f"{essay_id} from status {essay_state.current_status.value}.",
                    extra={
                        "phase": phase_name,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

        except Exception as e:
            logger.error(
                f"Error in state transition for {phase_name}",
                extra={
                    "essay_id": essay_id,
                    "phase": phase_name,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def check_batch_completion_after_essay_update(
        self,
        essay_id: str,
        phase_name: PhaseName,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> None:
        """
        Check batch completion after individual essay state update.

        Args:
            essay_id: Essay identifier
            phase_name: Processing phase for batch coordination
            session: Database session
            correlation_id: Correlation ID for tracking
        """
        try:
            updated_essay_state = await self.repository.get_essay_state(essay_id, session)
            if updated_essay_state:
                await self.batch_coordinator.check_batch_completion(
                    essay_state=updated_essay_state,
                    phase_name=phase_name,
                    correlation_id=correlation_id,
                    session=session,
                )
        except Exception as e:
            logger.error(
                f"Error checking batch completion for {phase_name.value}",
                extra={
                    "essay_id": essay_id,
                    "phase": phase_name.value,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )

    def _build_essay_metadata(
        self,
        essay_state: Any,
        phase_name: str,
        success: bool,
        result_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build essay metadata preserving existing commanded_phases.

        Args:
            essay_state: Current essay state
            phase_name: Current processing phase
            success: Whether the operation was successful
            result_metadata: Result-specific metadata

        Returns:
            Metadata dictionary for repository update
        """
        # Preserve existing commanded_phases metadata
        existing_commanded_phases = essay_state.processing_metadata.get("commanded_phases", [])

        # Ensure current phase is in commanded_phases
        if phase_name not in existing_commanded_phases:
            existing_commanded_phases.append(phase_name)

        # Build base metadata
        metadata = {
            "current_phase": phase_name,
            "commanded_phases": existing_commanded_phases,
            **result_metadata,  # Include phase-specific result metadata
        }

        return metadata
