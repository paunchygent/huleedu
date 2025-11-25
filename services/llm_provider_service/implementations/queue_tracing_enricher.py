"""Tracing and metadata enrichment helpers for queued requests."""

from __future__ import annotations

from common_core import LLMProviderType

from services.llm_provider_service.config import QueueProcessingMode
from services.llm_provider_service.queue_models import QueuedRequest


class QueueTracingEnricher:
    """Add provider and queue processing context to request metadata."""

    def __init__(self, queue_processing_mode: QueueProcessingMode) -> None:
        self.queue_processing_mode = queue_processing_mode

    def enrich_request_metadata(
        self,
        request: QueuedRequest,
        *,
        provider: LLMProviderType,
        model: str | None,
    ) -> None:
        """Enrich queued request metadata with provider-side context."""

        metadata = request.request_data.metadata or {}

        metadata["resolved_provider"] = provider.value
        metadata["queue_processing_mode"] = self.queue_processing_mode.value
        if model is not None:
            metadata["resolved_model"] = model

        request.request_data.metadata = metadata
