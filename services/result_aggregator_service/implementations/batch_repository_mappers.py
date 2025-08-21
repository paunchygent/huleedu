"""Database to domain model mappers for Result Aggregator Service."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.result_aggregator_service.models_db import BatchResult, EssayResult

logger = create_service_logger("result_aggregator.mappers")


class BatchRepositoryMappers:
    """Maps between database models and domain objects."""

    def __init__(self) -> None:
        """Initialize mapper."""
        self.logger = logger

    def map_batch_to_domain(self, batch: BatchResult) -> Dict[str, Any]:
        """Map BatchResult DB model to domain representation.

        Args:
            batch: BatchResult database model

        Returns:
            Dictionary representation of batch for domain use
        """
        return {
            "batch_id": batch.batch_id,
            "user_id": batch.user_id,
            "overall_status": batch.overall_status,
            "essay_count": batch.essay_count,
            "completed_essay_count": batch.completed_essay_count,
            "failed_essay_count": batch.failed_essay_count,
            "batch_metadata": batch.batch_metadata or {},
            "batch_error_detail": batch.batch_error_detail,
            "processing_started_at": (
                batch.processing_started_at.isoformat() if batch.processing_started_at else None
            ),
            "processing_completed_at": (
                batch.processing_completed_at.isoformat() if batch.processing_completed_at else None
            ),
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        }

    def map_essay_to_domain(self, essay: EssayResult) -> Dict[str, Any]:
        """Map EssayResult DB model to domain representation.

        Args:
            essay: EssayResult database model

        Returns:
            Dictionary representation of essay for domain use
        """
        return {
            "essay_id": essay.essay_id,
            "batch_id": essay.batch_id,
            "file_upload_id": essay.file_upload_id,
            "original_text_storage_id": essay.original_text_storage_id,
            # Spellcheck fields
            "spellcheck_status": essay.spellcheck_status,
            "spellcheck_correction_count": essay.spellcheck_correction_count,
            "spellcheck_corrected_text_storage_id": essay.spellcheck_corrected_text_storage_id,
            "spellcheck_error_detail": essay.spellcheck_error_detail,
            # CJ Assessment fields
            "cj_assessment_status": essay.cj_assessment_status,
            "cj_rank": essay.cj_rank,
            "cj_score": essay.cj_score,
            "cj_comparison_count": essay.cj_comparison_count,
            "cj_assessment_error_detail": essay.cj_assessment_error_detail,
            # Metadata
            "essay_metadata": essay.essay_metadata or {},
            "created_at": essay.created_at.isoformat() if essay.created_at else None,
            "updated_at": essay.updated_at.isoformat() if essay.updated_at else None,
        }

    def map_domain_to_batch(self, domain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map domain data to BatchResult DB model fields.

        Args:
            domain_data: Domain representation of batch

        Returns:
            Dictionary of fields for BatchResult model
        """
        db_fields = {
            "batch_id": domain_data.get("batch_id"),
            "user_id": domain_data.get("user_id"),
            "overall_status": domain_data.get("overall_status"),
            "essay_count": domain_data.get("essay_count", 0),
            "completed_essay_count": domain_data.get("completed_essay_count", 0),
            "failed_essay_count": domain_data.get("failed_essay_count", 0),
            "batch_metadata": domain_data.get("batch_metadata", {}),
        }

        # Handle optional fields
        if "batch_error_detail" in domain_data:
            db_fields["batch_error_detail"] = domain_data["batch_error_detail"]

        # Handle datetime fields
        if "processing_started_at" in domain_data and domain_data["processing_started_at"]:
            db_fields["processing_started_at"] = self._parse_datetime(
                domain_data["processing_started_at"]
            )
        if "processing_completed_at" in domain_data and domain_data["processing_completed_at"]:
            db_fields["processing_completed_at"] = self._parse_datetime(
                domain_data["processing_completed_at"]
            )

        return db_fields

    def map_domain_to_essay(self, domain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map domain data to EssayResult DB model fields.

        Args:
            domain_data: Domain representation of essay

        Returns:
            Dictionary of fields for EssayResult model
        """
        db_fields = {
            "essay_id": domain_data.get("essay_id"),
            "batch_id": domain_data.get("batch_id"),
        }

        # Handle optional fields
        optional_fields = [
            "file_upload_id",
            "original_text_storage_id",
            "spellcheck_status",
            "spellcheck_correction_count",
            "spellcheck_corrected_text_storage_id",
            "spellcheck_error_detail",
            "cj_assessment_status",
            "cj_rank",
            "cj_score",
            "cj_comparison_count",
            "cj_assessment_error_detail",
            "essay_metadata",
        ]

        for field in optional_fields:
            if field in domain_data:
                db_fields[field] = domain_data[field]

        return db_fields

    def _parse_datetime(self, dt_value: Any) -> Optional[datetime]:
        """Parse datetime from various formats.

        Args:
            dt_value: Datetime value (string, datetime, or None)

        Returns:
            datetime object or None
        """
        if dt_value is None:
            return None
        if isinstance(dt_value, datetime):
            return dt_value
        if isinstance(dt_value, str):
            try:
                return datetime.fromisoformat(dt_value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                self.logger.warning(f"Could not parse datetime: {dt_value}")
                return None
        return None
