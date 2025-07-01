"""Production PostgreSQL repository implementation for Batch Orchestrator Service."""

from __future__ import annotations

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_orchestrator_service.implementations.batch_configuration_manager import (
    BatchConfigurationManager,
)
from services.batch_orchestrator_service.implementations.batch_context_operations import (
    BatchContextOperations,
)
from services.batch_orchestrator_service.implementations.batch_crud_operations import (
    BatchCrudOperations,
)
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import (
    BatchDatabaseInfrastructure,
)
from services.batch_orchestrator_service.implementations.batch_pipeline_state_manager import (
    BatchPipelineStateManager,
)
from services.batch_orchestrator_service.models_db import BatchEssay
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol
from sqlalchemy import delete, select

from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus


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
            batch_id,
            pipeline_state,
        )
        return result

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve pipeline processing state for a batch."""
        result: dict | None = await self.pipeline_manager.get_processing_pipeline_state(batch_id)
        return result

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
        correlation_id: str | None = None,
    ) -> bool:
        """Atomically update phase status if current status matches expected."""
        result: bool = await self.pipeline_manager.update_phase_status_atomically(
            batch_id,
            phase_name,
            expected_status,
            new_status,
            completion_timestamp,
            correlation_id,
        )
        return result

    # Context operations - delegated to context_ops
    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: str | None = None,
    ) -> bool:
        """Store batch context information."""
        result: bool = await self.context_ops.store_batch_context(batch_id, registration_data, correlation_id)
        return result

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve batch context information."""
        result: BatchRegistrationRequestV1 | None = await self.context_ops.get_batch_context(
            batch_id,
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
            batch_id,
            snapshot_name,
            pipeline_definition,
            configuration_version,
            description,
        )
        return result

    async def get_phase_status_history(self, batch_id: str) -> list[dict]:
        """Get phase status history for a batch."""
        result: list[dict] = await self.config_manager.get_phase_status_history(batch_id)
        return result

    # Essay storage operations - proper PostgreSQL implementation
    async def store_batch_essays(self, batch_id: str, essays: list) -> bool:
        """Store essay data from BatchEssaysReady event in PostgreSQL."""
        logger = create_service_logger("bos.repository.batch_essays")

        try:
            async with self.db_infrastructure.session() as session:
                # First, remove any existing essays for this batch (idempotency)
                await session.execute(delete(BatchEssay).where(BatchEssay.batch_id == batch_id))

                # Insert new essays - essays are EssayProcessingInputRefV1 objects
                for essay_obj in essays:
                    # Create content reference from the essay object
                    content_reference = {
                        "text_storage_id": essay_obj.text_storage_id,
                        "type": "text_content",
                    }

                    essay_record = BatchEssay(
                        batch_id=batch_id,
                        essay_id=essay_obj.essay_id,
                        content_reference=content_reference,
                        student_metadata={},  # Not available in EssayProcessingInputRefV1
                        processing_metadata={},  # Not available in EssayProcessingInputRefV1
                    )
                    session.add(essay_record)

                await session.commit()
                logger.info(f"Stored {len(essays)} essays for batch {batch_id} in PostgreSQL")
                return True

        except Exception as e:
            logger.error(f"Failed to store essays for batch {batch_id}: {e}")
            return False

    async def get_batch_essays(self, batch_id: str) -> list | None:
        """Retrieve stored essay data from PostgreSQL."""
        logger = create_service_logger("bos.repository.batch_essays")

        try:
            async with self.db_infrastructure.session() as session:
                result = await session.execute(
                    select(BatchEssay).where(BatchEssay.batch_id == batch_id),
                )
                essay_records = result.scalars().all()

                if not essay_records:
                    logger.warning(f"No essays found for batch {batch_id} in PostgreSQL")
                    return None

                # Convert database records back to EssayProcessingInputRefV1 objects
                # as expected by the PipelinePhaseInitiatorProtocol
                essays = []
                for record in essay_records:
                    # Reconstruct EssayProcessingInputRefV1 object from stored data
                    essay_obj = EssayProcessingInputRefV1(
                        essay_id=record.essay_id,
                        text_storage_id=record.content_reference.get("text_storage_id", ""),
                    )
                    essays.append(essay_obj)

                logger.info(f"Retrieved {len(essays)} essays for batch {batch_id} from PostgreSQL")
                return essays

        except Exception as e:
            logger.error(f"Failed to retrieve essays for batch {batch_id}: {e}")
            return None
