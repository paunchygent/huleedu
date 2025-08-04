"""
Test data builders for Essay Lifecycle Service tests.

Provides utilities for creating test scenarios consistently across test suites,
following the builder pattern for maintainable and reusable test data creation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.constants import (
    ELS_PHASE_STATUS_MAPPING,
    MetadataKey,
)
from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.protocols import (
    EssayRepositoryProtocol,
    EssayState as ProtocolEssayState,
)


class EssayTestDataBuilder:
    """Builder pattern for creating test scenarios consistently."""

    @staticmethod
    async def create_batch_with_phase_distribution(
        repository: EssayRepositoryProtocol,
        batch_id: str,
        phase_distributions: dict[str, int],
    ) -> list[EssayState | ProtocolEssayState]:
        """
        Create essays with specific phase distributions for testing.

        Args:
            repository: Repository instance to use for creation
            batch_id: Batch identifier for all essays
            phase_distributions: Dict mapping phase names to counts
                Example: {"spellcheck": 3, "cj_assessment": 2}

        Returns:
            List of created essay states
        """
        essays = []
        correlation_id = uuid4()

        for phase_name, count in phase_distributions.items():
            # Convert string phase name to PhaseName enum
            try:
                phase_enum = PhaseName(phase_name)
                phase_statuses = ELS_PHASE_STATUS_MAPPING.get(phase_enum, [])
            except ValueError:
                continue  # Skip unknown phases

            if not phase_statuses:
                continue

            for i in range(count):
                essay_id = f"{batch_id}-{phase_name}-{i}"
                # Cycle through statuses for variety
                status = phase_statuses[i % len(phase_statuses)]

                # Create essay record
                essay_state = await repository.create_essay_record(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    correlation_id=correlation_id,
                )

                # Update to target status if not already UPLOADED
                if status != EssayStatus.UPLOADED:
                    await repository.update_essay_state(
                        essay_id=essay_id,
                        new_status=status,
                        metadata={
                            MetadataKey.CURRENT_PHASE: phase_name,
                            MetadataKey.COMMANDED_PHASES: [phase_name],
                            "test_builder": "create_batch_with_phase_distribution",
                        },
                        correlation_id=correlation_id,
                    )
                    # Get updated essay state
                    updated_essay = await repository.get_essay_state(essay_id)
                    assert updated_essay is not None
                    essays.append(updated_essay)
                else:
                    essays.append(essay_state)

        return essays

    @staticmethod
    async def create_essay_with_full_lifecycle(
        repository: EssayRepositoryProtocol,
        essay_id: str,
        batch_id: str,
        target_status: EssayStatus,
    ) -> EssayState | ProtocolEssayState:
        """
        Create an essay and progress it through lifecycle to target status.

        Args:
            repository: Repository instance to use
            essay_id: Unique essay identifier
            batch_id: Batch identifier
            target_status: Final status to reach

        Returns:
            Essay state at target status
        """
        correlation_id = uuid4()

        # Create initial essay
        essay_state = await repository.create_essay_record(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # If target is UPLOADED, we're done
        if target_status == EssayStatus.UPLOADED:
            return essay_state

        # Build lifecycle path to target status
        lifecycle_path = EssayTestDataBuilder._build_lifecycle_path(target_status)

        # Apply each transition
        for status in lifecycle_path:
            await repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={
                    "lifecycle_progression": True,
                    "target_status": target_status.value,
                    "transition_timestamp": datetime.now(UTC).isoformat(),
                },
                correlation_id=correlation_id,
            )

        # Return final state
        final_state = await repository.get_essay_state(essay_id)
        assert final_state is not None
        return final_state

    @staticmethod
    def _build_lifecycle_path(target_status: EssayStatus) -> list[EssayStatus]:
        """
        Build a realistic path to reach target status.

        Args:
            target_status: The desired final status

        Returns:
            List of statuses representing a realistic progression
        """
        # Common progression patterns
        spellcheck_path = [
            EssayStatus.READY_FOR_PROCESSING,
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
        ]

        cj_assessment_path = [
            EssayStatus.READY_FOR_PROCESSING,  
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
        ]

        nlp_path = [
            EssayStatus.READY_FOR_PROCESSING,
            EssayStatus.AWAITING_NLP,
            EssayStatus.NLP_IN_PROGRESS,
        ]

        ai_feedback_path = [
            EssayStatus.READY_FOR_PROCESSING,
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.AI_FEEDBACK_IN_PROGRESS,
        ]

        # Map target statuses to their paths
        status_paths = {
            # Spellcheck progression
            EssayStatus.AWAITING_SPELLCHECK: [EssayStatus.READY_FOR_PROCESSING],
            EssayStatus.SPELLCHECKING_IN_PROGRESS: spellcheck_path[:2],
            EssayStatus.SPELLCHECKED_SUCCESS: spellcheck_path,
            EssayStatus.SPELLCHECK_FAILED: spellcheck_path,

            # CJ Assessment progression
            EssayStatus.AWAITING_CJ_ASSESSMENT: [EssayStatus.READY_FOR_PROCESSING],
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS: cj_assessment_path[:2],
            EssayStatus.CJ_ASSESSMENT_SUCCESS: cj_assessment_path,
            EssayStatus.CJ_ASSESSMENT_FAILED: cj_assessment_path,

            # NLP progression
            EssayStatus.AWAITING_NLP: [EssayStatus.READY_FOR_PROCESSING],
            EssayStatus.NLP_IN_PROGRESS: nlp_path[:2],
            EssayStatus.NLP_SUCCESS: nlp_path,
            EssayStatus.NLP_FAILED: nlp_path,

            # AI Feedback progression
            EssayStatus.AWAITING_AI_FEEDBACK: [EssayStatus.READY_FOR_PROCESSING],
            EssayStatus.AI_FEEDBACK_IN_PROGRESS: ai_feedback_path[:2],
            EssayStatus.AI_FEEDBACK_SUCCESS: ai_feedback_path,
            EssayStatus.AI_FEEDBACK_FAILED: ai_feedback_path,

            # Other statuses
            EssayStatus.READY_FOR_PROCESSING: [],
            EssayStatus.ALL_PROCESSING_COMPLETED: [
                EssayStatus.READY_FOR_PROCESSING,
                EssayStatus.AWAITING_SPELLCHECK,
                EssayStatus.SPELLCHECKED_SUCCESS,
            ],
        }

        return status_paths.get(target_status, []) + [target_status]

    @staticmethod
    async def create_essays_with_metadata_patterns(
        repository: EssayRepositoryProtocol,
        batch_id: str,
        metadata_patterns: list[dict[str, Any]],
    ) -> list[EssayState | ProtocolEssayState]:
        """
        Create essays with specific metadata patterns for testing.

        Args:
            repository: Repository instance to use
            batch_id: Batch identifier
            metadata_patterns: List of metadata dicts to apply

        Returns:
            List of created essays with applied metadata
        """
        essays = []
        correlation_id = uuid4()

        for i, metadata_pattern in enumerate(metadata_patterns):
            essay_id = f"{batch_id}-metadata-{i}"

            # Create essay
            essay_state = await repository.create_essay_record(
                essay_id=essay_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
            )

            # Apply metadata pattern
            await repository.update_essay_processing_metadata(
                essay_id=essay_id,
                metadata_updates=metadata_pattern,
                correlation_id=correlation_id,
            )

            # Get the updated essay state after metadata changes
            updated_essay = await repository.get_essay_state(essay_state.essay_id)
            assert updated_essay is not None
            essays.append(updated_essay)

        return essays

    @staticmethod  
    def create_realistic_essay_data(
        essay_id: str,
        batch_id: str,
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Create realistic essay data with sensible defaults.

        Args:
            essay_id: Essay identifier
            batch_id: Batch identifier
            **overrides: Values to override defaults

        Returns:
            Dictionary of essay data suitable for creation methods
        """
        base_data = {
            "internal_essay_id": essay_id,
            "batch_id": batch_id,
            "original_file_name": f"{essay_id}.docx",
            "file_size": 1024 * 50,  # 50KB default
            "content_hash": f"md5-hash-{essay_id}",
            "initial_status": EssayStatus.UPLOADED.value,
            "created_via": "test_data_builder",
        }

        # Apply overrides
        base_data.update(overrides)
        return base_data