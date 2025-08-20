"""
Database-domain mapping functions for Essay Lifecycle Service.

Pure functions for converting between database models and domain objects
following DDD principles and SRP.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from common_core.domain_enums import ContentType

from services.essay_lifecycle_service.domain_models import EssayState as ConcreteEssayState
from services.essay_lifecycle_service.models_db import EssayStateDB

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState


class EssayRepositoryMappers:
    """Pure mapping functions for DB ↔ domain conversions."""

    @staticmethod
    def db_to_essay_state(db_essay: EssayStateDB) -> ConcreteEssayState:
        """Convert database model to EssayState domain object."""
        # Convert timeline from string to datetime
        timeline_converted = {k: datetime.fromisoformat(v) for k, v in db_essay.timeline.items()}

        return ConcreteEssayState(
            essay_id=db_essay.essay_id,
            batch_id=db_essay.batch_id,
            current_status=db_essay.current_status,
            processing_metadata=db_essay.processing_metadata,
            timeline=timeline_converted,
            storage_references={ContentType(k): v for k, v in db_essay.storage_references.items()},
            created_at=db_essay.created_at,
            updated_at=db_essay.updated_at,
        )

    @staticmethod
    def essay_state_to_db_dict(essay_state: EssayState) -> dict[str, Any]:
        """Convert EssayState domain object to database dictionary."""
        return {
            "essay_id": essay_state.essay_id,
            "batch_id": essay_state.batch_id,
            "current_status": essay_state.current_status,
            "processing_metadata": essay_state.processing_metadata,
            "timeline": {k: v.isoformat() for k, v in essay_state.timeline.items()},
            "storage_references": {k.value: v for k, v in essay_state.storage_references.items()},
            "created_at": essay_state.created_at.replace(tzinfo=None),
            "updated_at": essay_state.updated_at.replace(tzinfo=None),
        }
