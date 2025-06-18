"""
Protocol definitions for Batch Conductor Service.

This module defines behavioral contracts for pipeline dependency resolution,
event-driven state management, and configuration-driven pipeline generation.
"""

from __future__ import annotations

from typing import Any, Protocol

from common_core.events.envelope import EventEnvelope


class BatchStateRepositoryProtocol(Protocol):
    """
    Protocol for batch processing state management using Redis cache + PostgreSQL persistence.

    Tracks essay processing completion status across all specialized services for
    intelligent pipeline dependency resolution and optimization.
    """

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """
        Record completion of a processing step for an essay.

        Args:
            batch_id: Batch identifier
            essay_id: Essay identifier
            step_name: Processing step name (e.g., 'spellcheck', 'ai_feedback')
            metadata: Optional completion metadata

        Returns:
            True if recorded successfully, False otherwise
        """
        ...

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """
        Get all completed processing steps for an essay.

        Args:
            batch_id: Batch identifier
            essay_id: Essay identifier

        Returns:
            Set of completed step names
        """
        ...

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """
        Get completion summary for all essays in a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            Dictionary mapping step_name -> {'completed': count, 'total': count}
        """
        ...

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """
        Check if a processing step is complete for all essays in a batch.

        Args:
            batch_id: Batch identifier
            step_name: Processing step name

        Returns:
            True if step is complete for all essays, False otherwise
        """
        ...


class PipelineRulesProtocol(Protocol):
    """
    Protocol for pipeline dependency resolution and optimization logic.

    Responsible for analyzing requested pipelines and determining the optimal
    execution sequence based on dependencies and current batch state.
    """

    async def resolve_pipeline_dependencies(
        self, requested_pipeline: str, current_batch_state: dict[str, set[str]]
    ) -> dict[str, list[str]]:
        """Resolve pipeline dependencies based on current batch state."""
        ...

    async def validate_pipeline_compatibility(
        self, pipeline_name: str, batch_metadata: dict | None = None
    ) -> tuple[bool, str | None]:
        """Validate if pipeline can be executed with given batch metadata."""
        ...


class KafkaEventConsumerProtocol(Protocol):
    """
    Protocol for Kafka event consumption in BCS.

    Provides processing result event consumption with idempotency and state management.
    """

    async def start_consuming(self) -> None:
        """
        Start consuming Kafka events.

        Raises:
            RuntimeError: If consumer is already running or configuration is invalid
        """
        ...

    async def stop_consuming(self) -> None:
        """
        Stop consuming Kafka events gracefully.
        """
        ...

    async def is_consuming(self) -> bool:
        """
        Check if consumer is actively consuming events.

        Returns:
            True if consuming, False otherwise
        """
        ...


class PipelineGeneratorProtocol(Protocol):
    """
    Protocol for configuration-driven pipeline definition access.

    Provides access to pipeline configurations loaded from YAML files
    with proper validation and error handling.
    """

    async def get_pipeline_definition(self, pipeline_name: str) -> dict | None:
        """Get pipeline definition by name."""
        ...

    async def list_available_pipelines(self) -> list[str]:
        """
        List all available pipeline names.

        Returns:
            List of pipeline names available in configuration
        """
        ...

    async def validate_pipeline_config(self) -> bool:
        """Validate pipeline configuration."""
        ...

    def get_pipeline_steps(self, pipeline_name: str) -> list[str] | None:
        """Get steps for a named pipeline configuration (synchronous version)."""
        ...

    def get_all_pipeline_names(self) -> list[str]:
        """Get all available pipeline names."""
        ...

    def validate_configuration(self) -> tuple[bool, str]:
        """Validate pipeline configuration for cycles and dependencies."""
        ...


class DlqProducerProtocol(Protocol):
    """Protocol for Dead Letter Queue message production."""

    async def publish_to_dlq(
        self,
        base_topic: str,
        failed_event_envelope: EventEnvelope | dict,
        dlq_reason: str,
        additional_metadata: dict | None = None,
    ) -> bool:
        """
        Publish failed event to Dead Letter Queue.

        Args:
            base_topic: Original topic name (DLQ topic will be base_topic.DLQ)
            failed_event_envelope: The original event that failed processing
            dlq_reason: Reason for DLQ (e.g., "DependencyCycleDetected", "ValidationFailed")
            additional_metadata: Optional additional context

        Returns:
            True if published successfully, False otherwise
        """
        ...


class PipelineResolutionServiceProtocol(Protocol):
    """
    Protocol for the main pipeline resolution service.

    Orchestrates pipeline rules, batch state repository, and pipeline generator
    to provide complete pipeline resolution responses.
    """

    async def resolve_optimal_pipeline(
        self,
        batch_id: str,
        requested_pipeline: str,
        additional_metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Resolve optimal pipeline configuration for a batch."""
        ...
