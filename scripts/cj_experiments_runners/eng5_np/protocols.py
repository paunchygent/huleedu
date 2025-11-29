"""Protocol definitions for ENG5 NP runner components.

Defines interfaces for mode handlers and service dependencies,
enabling dependency injection and testability.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


@runtime_checkable
class ModeHandlerProtocol(Protocol):
    """Protocol for CLI mode handlers.

    Each mode (PLAN, DRY_RUN, ANCHOR_ALIGN_TEST, EXECUTE) implements this
    protocol to provide mode-specific execution logic.
    """

    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,
    ) -> int:
        """Execute the mode-specific logic.

        Args:
            settings: Validated runner configuration
            inventory: Collected file inventory (anchors, students, prompt)
            paths: Path configuration for the runner

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        ...


@runtime_checkable
class ContentUploaderProtocol(Protocol):
    """Protocol for Content Service interactions.

    Abstracts essay upload operations for testability.
    """

    async def upload_essays(
        self,
        records: list,
        content_service_url: str,
    ) -> dict[str, str]:
        """Upload essays to Content Service.

        Args:
            records: List of FileRecord objects to upload
            content_service_url: Base URL for Content Service

        Returns:
            Mapping of file checksum to storage_id
        """
        ...


@runtime_checkable
class AnchorRegistrarProtocol(Protocol):
    """Protocol for CJ Assessment Service anchor registration.

    Abstracts anchor registration for testability.
    """

    async def register_anchors(
        self,
        anchors: list,
        assignment_id: str,
        cj_service_url: str,
    ) -> list:
        """Register anchor essays with CJ Assessment Service.

        Args:
            anchors: List of FileRecord objects representing anchors
            assignment_id: Assignment ID to bind anchors to
            cj_service_url: Base URL for CJ Assessment Service

        Returns:
            List of registration results
        """
        ...


@runtime_checkable
class KafkaPublisherProtocol(Protocol):
    """Protocol for Kafka event publishing.

    Abstracts Kafka operations for testability.
    """

    async def publish_envelope(
        self,
        envelope: dict,
        settings: RunnerSettings,
    ) -> None:
        """Publish event envelope to Kafka.

        Args:
            envelope: Event envelope to publish
            settings: Runner settings with Kafka configuration
        """
        ...


@runtime_checkable
class HydratorProtocol(Protocol):
    """Protocol for assessment result hydration.

    Abstracts result collection and artefact generation.
    """

    def get_run_artefact(self) -> dict:
        """Get the complete run artefact data.

        Returns:
            Dictionary containing bt_summary, llm_comparisons, etc.
        """
        ...

    def runner_status(self) -> dict:
        """Get current runner status.

        Returns:
            Dictionary with observed events, timing, etc.
        """
        ...


@runtime_checkable
class ReportGeneratorProtocol(Protocol):
    """Protocol for alignment report generation.

    Abstracts report generation for testability.
    """

    def generate(
        self,
        hydrator: HydratorProtocol | None,
        anchor_grade_map: dict[str, str],
        system_prompt_text: str | None,
        rubric_text: str | None,
        batch_id: str,
        output_dir: Path,
    ) -> Path:
        """Generate alignment report.

        Args:
            hydrator: Hydrator with collected results (or None)
            anchor_grade_map: Mapping of anchor_id to expected grade
            system_prompt_text: System prompt used (for reproducibility)
            rubric_text: Rubric used (for reproducibility)
            batch_id: Batch identifier
            output_dir: Directory for report output

        Returns:
            Path to generated report file
        """
        ...
