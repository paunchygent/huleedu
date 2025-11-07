"""
Prompt reference helper utilities for tests.

Ensures all test suites build StorageReferenceMetadata objects using the
same pattern so Kafka and HTTP payloads consistently reference Content
Service storage identifiers for student prompts.
"""

from __future__ import annotations

from typing import Any

from common_core.domain_enums import ContentType
from common_core.metadata_models import StorageReferenceMetadata

__all__ = ["make_prompt_ref", "serialize_prompt_ref", "make_prompt_ref_payload"]


def make_prompt_ref(storage_id: str, path_hint: str | None = None) -> StorageReferenceMetadata:
    """
    Create a StorageReferenceMetadata instance for the given storage identifier.

    Args:
        storage_id: Content Service storage identifier (or descriptive label for mocked flows)
        path_hint: Optional path hint used in certain storage backends
    """
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, storage_id, path_hint)
    return prompt_ref


def serialize_prompt_ref(
    prompt_ref: StorageReferenceMetadata | None,
) -> dict[str, Any] | None:
    """Serialize a prompt reference for JSON payloads."""
    if prompt_ref is None:
        return None
    return prompt_ref.model_dump(mode="json")


def make_prompt_ref_payload(label: str, path_hint: str | None = None) -> dict[str, Any]:
    """Convenience helper to build and serialize a prompt reference in one step."""
    return serialize_prompt_ref(make_prompt_ref(label, path_hint)) or {}
