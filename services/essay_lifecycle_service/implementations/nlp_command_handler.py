"""NLP command handler for Essay Lifecycle Service.

This module handles NLP initiation commands from the Batch Orchestrator Service,
following the same architectural pattern as the spellcheck command handler.
"""

from uuid import UUID

from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.domain_enums import Language
from huleedu_service_libs.logging_utils import create_service_logger

from sqlalchemy.ext.asyncio import async_sessionmaker

from services.essay_lifecycle_service.protocols import (
    EssayRepositoryProtocol,
    SpecializedServiceRequestDispatcher,
)



logger = create_service_logger("essay_lifecycle.nlp_command_handler")


class NlpCommandHandler:
    """Handles NLP initiation commands from Batch Orchestrator Service."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        session_factory: async_sessionmaker,
    ) -> None:
        """Initialize with dependencies."""
        self.repository = repository
        self.request_dispatcher = request_dispatcher
        self.session_factory = session_factory

    async def process_initiate_nlp_command(
        self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID
    ) -> None:
        """Process NLP initiation command from Batch Orchestrator Service.
        
        This method:
        1. Updates essay states to track NLP phase initiation
        2. Forwards requests to NLP service via dispatcher
        
        This follows the same pattern as spellcheck, maintaining architectural consistency.
        
        Args:
            command_data: The NLP initiation command data from BOS
            correlation_id: Correlation ID for tracking the request flow
        """
        logger.info(
            "Processing NLP initiation command",
            extra={
                "batch_id": command_data.entity_id,
                "essays_count": len(command_data.essays_to_process),
                "correlation_id": str(correlation_id),
            },
        )
        
        # Track successfully transitioned essays for forwarding
        successfully_transitioned = []
        
        async with self.session_factory() as session:
            async with session.begin():
                # Update essay states to reflect NLP processing has been initiated
                for essay_ref in command_data.essays_to_process:
                    try:
                        essay_state = await self.repository.get_essay_state(essay_ref.essay_id)
                        if essay_state:
                            # Update metadata to track NLP phase initiation
                            metadata_updates = {
                                "nlp_phase": "initiated",
                                "nlp_initiated_at": str(correlation_id),
                                "current_phase": "nlp_analysis",
                            }
                            
                            await self.repository.update_essay_processing_metadata(
                                essay_id=essay_ref.essay_id,
                                metadata_updates=metadata_updates,
                                session=session,
                                correlation_id=correlation_id,
                            )
                            
                            successfully_transitioned.append(essay_ref)
                            
                            logger.info(
                                f"Updated essay {essay_ref.essay_id} state for NLP phase",
                                extra={
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to update state for essay {essay_ref.essay_id}: {e}",
                            extra={
                                "batch_id": command_data.entity_id,
                                "correlation_id": str(correlation_id),
                                "error": str(e),
                            },
                        )
                
                # Dispatch NLP requests to NLP service
                if successfully_transitioned:
                    batch_id = command_data.entity_id
                    if batch_id is None:
                        logger.error(
                            "Cannot dispatch NLP requests: batch_id is None",
                            extra={
                                "correlation_id": str(correlation_id),
                                "essays_count": len(successfully_transitioned),
                            },
                        )
                        return
                    
                    await self.request_dispatcher.dispatch_nlp_requests(
                        essays_to_process=successfully_transitioned,
                        language=Language(command_data.language),
                        batch_id=batch_id,
                        correlation_id=correlation_id,
                        session=session,
                    )
                
                logger.info(
                    f"Completed NLP phase initiation for batch {command_data.entity_id}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "essays_processed": len(successfully_transitioned),
                        "essays_total": len(command_data.essays_to_process),
                    },
                )