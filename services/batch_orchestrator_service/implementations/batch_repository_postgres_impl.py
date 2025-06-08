"""Production PostgreSQL repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

from api_models import BatchRegistrationRequestV1
from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from implementations.batch_configuration_manager import BatchConfigurationManager
from implementations.batch_context_operations import BatchContextOperations
from implementations.batch_crud_operations import BatchCrudOperations
from implementations.batch_database_infrastructure import BatchDatabaseInfrastructure
from implementations.batch_pipeline_state_manager import BatchPipelineStateManager
from protocols import BatchRepositoryProtocol


class PostgreSQLBatchRepositoryImpl(BatchRepositoryProtocol):
    """Production PostgreSQL implementation of BatchRepositoryProtocol."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the PostgreSQL repository with helper modules."""
        self.settings = settings
        self.logger = create_service_logger("bos.repository.postgres")

        # Initialize database infrastructure
        self.db_infrastructure = BatchDatabaseInfrastructure(settings)

        # Initialize helper modules
        self.crud_ops = BatchCrudOperations(self.db_infrastructure)
        self.pipeline_manager = BatchPipelineStateManager(self.db_infrastructure)
        self.context_ops = BatchContextOperations(self.db_infrastructure)
        self.config_manager = BatchConfigurationManager(self.db_infrastructure)

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        await self.db_infrastructure.initialize_db_schema()

    # Basic CRUD operations - delegated to crud_ops
    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve batch data by ID."""
        result: dict | None = await self.crud_ops.get_batch_by_id(batch_id)
        return result

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch record."""
        result: dict = await self.crud_ops.create_batch(batch_data)
        return result

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Update the status of an existing batch."""
        result: bool = await self.crud_ops.update_batch_status(batch_id, new_status)
        return result

    # Pipeline state operations - delegated to pipeline_manager
    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Save pipeline processing state for a batch."""
        result: bool = await self.pipeline_manager.save_processing_pipeline_state(
            batch_id, pipeline_state
        )
        return result

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve pipeline processing state for a batch."""
        result: dict | None = await self.pipeline_manager.get_processing_pipeline_state(batch_id)
        return result

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: str,
        expected_status: str,
        new_status: str,
        completion_timestamp: str | None = None,
    ) -> bool:
        """Atomically update phase status if current status matches expected."""
        result: bool = await self.pipeline_manager.update_phase_status_atomically(
            batch_id, phase_name, expected_status, new_status, completion_timestamp
        )
        return result

    # Context operations - delegated to context_ops
    async def store_batch_context(
        self, batch_id: str, registration_data: BatchRegistrationRequestV1
    ) -> bool:
        """Store batch context information."""
        result: bool = await self.context_ops.store_batch_context(batch_id, registration_data)
        return result

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve batch context information."""
        result: BatchRegistrationRequestV1 | None = await self.context_ops.get_batch_context(
            batch_id
        )
        return result

    # Configuration management - delegated to config_manager
    async def create_configuration_snapshot(
        self,
        batch_id: str,
        snapshot_name: str,
        pipeline_definition: dict,
        configuration_version: str,
        description: str | None = None,
    ) -> bool:
        """Create a configuration snapshot for a batch."""
        result: bool = await self.config_manager.create_configuration_snapshot(
            batch_id, snapshot_name, pipeline_definition, configuration_version, description
        )
        return result

    async def get_phase_status_history(self, batch_id: str) -> list[dict]:
        """Get phase status history for a batch."""
        result: list[dict] = await self.config_manager.get_phase_status_history(batch_id)
        return result
