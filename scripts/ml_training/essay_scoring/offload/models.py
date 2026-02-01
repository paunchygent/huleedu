"""Request/response models for the Hemma embedding offload server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmbedRequest(BaseModel):
    """Batch embedding request.

    Notes:
    - `model_name` is validated against the server's configured model to prevent accidental
      downloads and cache fragmentation.
    - Response is a binary `.npy` payload (float32 matrix) for throughput.
    """

    model_config = ConfigDict(extra="forbid")

    texts: list[str] = Field(..., min_length=1, description="Texts to embed.")
    model_name: str | None = Field(
        default=None, description="Must match the server-configured model if provided."
    )
    max_length: int | None = Field(
        default=None, ge=8, le=4096, description="Tokenization max length override (optional)."
    )
    batch_size: int | None = Field(
        default=None, ge=1, le=256, description="Batch size override (optional)."
    )
