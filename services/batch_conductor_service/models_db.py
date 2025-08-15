"""
Database models for Batch Conductor Service.

Defines SQLAlchemy models for persistent storage of phase completions
and other batch processing state.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base: Any = declarative_base()


class PhaseCompletion(Base):
    """
    Persistent record of batch phase completions.
    
    This table stores permanent records of which phases have completed
    for each batch, enabling dependency resolution even weeks or months
    after the phases were executed.
    
    Attributes:
        id: Primary key
        batch_id: Identifier of the batch
        phase_name: Name of the completed phase (e.g., "spellcheck", "ai_feedback")
        completed: Whether the phase completed successfully
        completed_at: Timestamp when the phase completed
        phase_metadata: Additional phase-specific metadata (optional)
    """
    
    __tablename__ = "phase_completions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(255), nullable=False)
    phase_name = Column(String(100), nullable=False)
    completed = Column(Boolean, nullable=False, default=True)
    completed_at = Column(
        DateTime(timezone=True), 
        nullable=False,
        server_default=func.now()
    )
    phase_metadata = Column(JSONB, nullable=True)
    
    # Unique constraint ensures only one record per batch/phase combination
    __table_args__ = (
        UniqueConstraint("batch_id", "phase_name", name="uq_batch_phase"),
        Index("idx_phase_completions_batch", "batch_id"),
        Index("idx_phase_completions_batch_completed", "batch_id", "completed"),
    )
    
    def __repr__(self) -> str:
        """String representation of PhaseCompletion."""
        return (
            f"<PhaseCompletion(batch_id={self.batch_id!r}, "
            f"phase_name={self.phase_name!r}, completed={self.completed})>"
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "phase_name": self.phase_name,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "phase_metadata": self.phase_metadata,
        }