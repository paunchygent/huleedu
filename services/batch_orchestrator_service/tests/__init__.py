"""Shared test helpers for Batch Orchestrator Service tests."""

from __future__ import annotations

from common_core.domain_enums import ContentType
from common_core.metadata_models import StorageReferenceMetadata

__all__ = ["make_prompt_ref"]


def make_prompt_ref(storage_id: str = "prompt-storage-id") -> StorageReferenceMetadata:
    """Create a StorageReferenceMetadata object for the student prompt."""

    return StorageReferenceMetadata(
        references={
            ContentType.STUDENT_PROMPT_TEXT: {
                "storage_id": storage_id,
                "path": "",
            }
        }
    )
