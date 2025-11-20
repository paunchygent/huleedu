from pydantic import BaseModel, Field

from common_core.metadata_models import StorageReferenceMetadata


class BatchPromptAmendmentRequest(BaseModel):
    """Attach or replace the student prompt reference on an existing batch."""

    student_prompt_ref: StorageReferenceMetadata = Field(
        description="Content Service reference for the student prompt"
    )
