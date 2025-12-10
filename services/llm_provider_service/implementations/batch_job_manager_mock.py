"""In-memory BatchJobManager implementation for BATCH_API scaffolding.

This mock manager treats provider batch jobs as instantly completing:
jobs are recorded in memory and item-level results are produced by
delegating to the ComparisonProcessorProtocol. It is intended for
early QueueProcessingMode.BATCH_API wiring and tests without any
external provider batch APIs or persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from common_core import LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.internal_models import (
    BatchJobItem,
    BatchJobItemStatus,
    BatchJobRef,
    BatchJobResult,
    BatchJobStatus,
)
from services.llm_provider_service.protocols import (
    BatchJobManagerProtocol,
    ComparisonProcessorProtocol,
)

logger = create_service_logger("llm_provider_service.batch_job_manager_mock")


class BatchJobManagerMock(BatchJobManagerProtocol):
    """Simple in-memory batch job manager with instant completion semantics."""

    def __init__(self, comparison_processor: ComparisonProcessorProtocol) -> None:
        self._comparison_processor = comparison_processor
        self._jobs: Dict[UUID, BatchJobRef] = {}
        self._job_items: Dict[UUID, List[BatchJobItem]] = {}

    async def schedule_job(
        self,
        provider: LLMProviderType,
        model: str,
        items: list[BatchJobItem],
    ) -> BatchJobRef:
        """Create a new in-memory job record and associate items with it."""

        job_id = uuid4()
        job_ref = BatchJobRef(
            job_id=job_id,
            provider=provider,
            model=model,
            status=BatchJobStatus.SCHEDULED,
            provider_job_id=None,
        )
        self._jobs[job_id] = job_ref
        self._job_items[job_id] = list(items)

        logger.info(
            "batch_api_job_scheduled",
            extra={
                "job_id": str(job_id),
                "provider": provider.value,
                "model": model,
                "item_count": len(items),
            },
        )

        return job_ref

    async def get_job_status(self, job: BatchJobRef) -> BatchJobRef:
        """Return the latest known status for the given job reference."""

        stored = self._jobs.get(job.job_id)
        return stored or job

    async def collect_results(self, job: BatchJobRef) -> list[BatchJobResult]:
        """Produce item-level results by invoking the comparison processor."""

        items = self._job_items.get(job.job_id, [])
        results: list[BatchJobResult] = []

        for item in items:
            response = await self._comparison_processor.process_comparison(
                provider=item.provider,
                user_prompt=item.user_prompt,
                correlation_id=item.correlation_id,
                prompt_blocks=item.prompt_blocks,
                **item.overrides,
            )
            results.append(
                BatchJobResult(
                    queue_id=item.queue_id,
                    provider=item.provider,
                    model=item.model,
                    status=BatchJobItemStatus.SUCCESS,
                    response=response,
                )
            )

        if job.job_id in self._jobs:
            self._jobs[job.job_id] = self._jobs[job.job_id].model_copy(
                update={
                    "status": BatchJobStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc),
                }
            )

        logger.info(
            "batch_api_job_completed",
            extra={
                "job_id": str(job.job_id),
                "provider": job.provider.value,
                "model": job.model,
                "item_count": len(results),
            },
        )

        return results

    async def cancel_job(self, job: BatchJobRef) -> None:
        """Mark a job as cancelled in memory (no-op for items)."""

        if job.job_id not in self._jobs:
            return

        self._jobs[job.job_id] = self._jobs[job.job_id].model_copy(
            update={"status": BatchJobStatus.CANCELLED}
        )

        logger.info(
            "batch_api_job_cancelled",
            extra={
                "job_id": str(job.job_id),
                "provider": job.provider.value,
                "model": job.model,
            },
        )
