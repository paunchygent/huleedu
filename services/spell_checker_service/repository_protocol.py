"""Protocol contract for spell-checker persistence layer.

Separated into its own module to avoid circular imports between
`protocols.py` and `models_db.py` while still providing a clear behavioural
contract that can be used for typing and mocking in tests.
"""

from __future__ import annotations

# Import only for typing (avoid runtime cycles)
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from common_core.status_enums import SpellcheckJobStatus as SCJobStatus

if TYPE_CHECKING:  # pragma: no cover
    from services.spell_checker_service.models_db import SpellcheckJob


class SpellcheckRepositoryProtocol(Protocol):
    """Behavioural contract for the persistence layer."""

    async def initialize_db_schema(self) -> None:  # Optional helper on startup
        """Create needed tables if they do not already exist."""

    async def create_job(
        self,
        batch_id: UUID,
        essay_id: UUID,
        *,
        language: str = "en",
    ) -> UUID:
        """Insert a new *pending* spell-check job and return its `job_id`."""

    async def update_status(
        self,
        job_id: UUID,
        status: SCJobStatus,
        *,
        error_message: str | None = None,
        processing_ms: int | None = None,
    ) -> None:
        """Update the status (and optionally error_message / processing_ms)."""

    async def add_tokens(
        self,
        job_id: UUID,
        tokens: list[tuple[str, list[str] | None, int | None, str | None]],
    ) -> None:
        """Bulk-insert tokens for a job.

        Each tuple represents `(token, suggestions, position, sentence)`.
        """

    async def get_job(self, job_id: UUID) -> "SpellcheckJob" | None:
        """Return the ORM model for the given job (or *None* if missing)."""
