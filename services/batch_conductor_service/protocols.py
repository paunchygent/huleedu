"""
Protocol definitions for Batch Conductor Service.

This module defines behavioral contracts for pipeline dependency resolution,
event-driven state management, and configuration-driven pipeline generation.
"""

from __future__ import annotations

from typing import Protocol

from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
    BCSPipelineDefinitionResponseV1,
)
from services.batch_conductor_service.pipeline_definitions import PipelineDefinition


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
        self, requested_pipeline: str, batch_id: str | None = None
    ) -> list[str]:
        """
        Resolve pipeline dependencies into an ordered execution sequence.

        Args:
            requested_pipeline: The target pipeline requested by the client
            batch_id: Batch ID for state-based optimization (optional)

        Returns:
            List of pipeline names in execution order

        Raises:
            ValueError: If requested pipeline is unknown or has circular dependencies
        """
        ...

    async def validate_pipeline_prerequisites(self, pipeline_name: str, batch_id: str) -> bool:
        """
        Validate that a pipeline's prerequisites are met for the given batch.

        Args:
            pipeline_name: Name of the pipeline to validate
            batch_id: Batch ID for state checking

        Returns:
            True if prerequisites are met, False otherwise
        """
        ...

    async def prune_completed_steps(self, pipeline_steps: list[str], batch_id: str) -> list[str]:
        """
        Remove already-completed steps from pipeline execution list.

        Args:
            pipeline_steps: Ordered list of pipeline steps
            batch_id: Batch ID for completion state checking

        Returns:
            Filtered list with only remaining steps to execute
        """
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

    async def get_pipeline_definition(self, pipeline_name: str) -> PipelineDefinition | None:
        """
        Retrieve pipeline definition by name.

        Args:
            pipeline_name: Name of the pipeline to retrieve

        Returns:
            PipelineDefinition object or None if not found
        """
        ...

    async def list_available_pipelines(self) -> list[str]:
        """
        List all available pipeline names.

        Returns:
            List of pipeline names available in configuration
        """
        ...

    async def validate_pipeline_config(self) -> bool:
        """
        Validate the current pipeline configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        ...


class PipelineResolutionServiceProtocol(Protocol):
    """
    Protocol for the main pipeline resolution service.

    Orchestrates pipeline rules, batch state repository, and pipeline generator
    to provide complete pipeline resolution responses.
    """

    async def resolve_pipeline_request(
        self, request: BCSPipelineDefinitionRequestV1
    ) -> BCSPipelineDefinitionResponseV1:
        """
        Resolve a complete pipeline request from BOS.

        Args:
            request: Pipeline resolution request from BOS

        Returns:
            Complete pipeline resolution response

        Raises:
            ValueError: If request is invalid
            RuntimeError: If batch state is unavailable
        """
        ...
