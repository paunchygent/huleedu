from __future__ import annotations

from random import Random
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.cj_core_logic.comparison_request_normalizer import (
    ComparisonRequestNormalizer,
    NormalizedComparisonRequest,
)
from services.cj_assessment_service.cj_core_logic.llm_batching_service import (
    BatchingModeService,
)
from services.cj_assessment_service.cj_core_logic.pair_generation import PairGenerationMode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.comparison_batch_orchestrator")


class ComparisonBatchOrchestrator:
    """Coordinate comparison submission lifecycle and persistence."""

    def __init__(
        self,
        *,
        batch_repository: CJBatchRepositoryProtocol,
        session_provider: SessionProviderProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        llm_interaction: LLMInteractionProtocol,
        matching_strategy: PairMatchingStrategyProtocol,
        settings: Settings,
        batching_service: BatchingModeService,
        request_normalizer: ComparisonRequestNormalizer,
    ) -> None:
        self.batch_repository = batch_repository
        self.session_provider = session_provider
        self.comparison_repository = comparison_repository
        self.instruction_repository = instruction_repository
        self.llm_interaction = llm_interaction
        self.matching_strategy = matching_strategy
        self.settings = settings
        self.batching_service = batching_service
        self.request_normalizer = request_normalizer

    async def submit_initial_batch(
        self,
        essays_for_api_model: list[EssayForComparison],
        cj_batch_id: int,
        request_data: CJAssessmentRequestData,
        correlation_id: UUID,
        log_extra: dict[str, Any],
        pair_generation_mode: PairGenerationMode = PairGenerationMode.COVERAGE,
    ) -> bool:
        normalized = self.request_normalizer.normalize(request_data)
        effective_batching_mode = self.batching_service.resolve_effective_mode(
            batch_config_overrides=normalized.batch_config_overrides,
            provider_override=normalized.provider_override,
        )
        log_extra_with_mode = {
            **log_extra,
            "effective_llm_batching_mode": effective_batching_mode.value,
        }
        logger.info(
            "Resolved comparison budget",
            extra={
                **log_extra_with_mode,
                "comparison_budget": normalized.max_pairs_cap,
                "comparison_budget_source": normalized.budget_source,
            },
        )

        async with self.session_provider.session() as session:
            await self._prepare_batch_state(
                session=session,
                cj_batch_id=cj_batch_id,
                normalized=normalized,
                correlation_id=correlation_id,
            )

            # Shuffle essays for initial batch to avoid deterministic bias
            # This ensures the first wave of pairs covers a random subset of essays
            rng = Random(self.settings.PAIR_GENERATION_SEED)
            essays_for_task_generation = list(essays_for_api_model)
            rng.shuffle(essays_for_task_generation)

            comparison_tasks = await pair_generation.generate_comparison_tasks(
                essays_for_comparison=essays_for_task_generation,
                session_provider=self.session_provider,
                comparison_repository=self.comparison_repository,
                instruction_repository=self.instruction_repository,
                matching_strategy=self.matching_strategy,
                cj_batch_id=cj_batch_id,
                max_pairwise_comparisons=normalized.max_pairs_cap,
                correlation_id=correlation_id,
                randomization_seed=self.settings.PAIR_GENERATION_SEED,
                mode=pair_generation_mode,
            )
            if not comparison_tasks:
                logger.warning(
                    "No comparison tasks generated for batch %s",
                    cj_batch_id,
                    extra=log_extra_with_mode,
                )
                return False

            self.batching_service.record_metrics(
                effective_mode=effective_batching_mode,
                request_count=len(comparison_tasks),
                request_type=request_data.cj_request_type,
            )

            batch_processor = BatchProcessor(
                session_provider=self.session_provider,
                llm_interaction=self.llm_interaction,
                settings=self.settings,
                batch_repository=self.batch_repository,
            )

            current_iteration = await self._get_current_iteration(session, cj_batch_id)
            iteration_metadata_context = self.batching_service.build_iteration_metadata_context(
                current_iteration=current_iteration
            )
            metadata_context = self.batching_service.build_metadata_context(
                cj_batch_id=cj_batch_id,
                cj_source=request_data.cj_source or "",
                cj_request_type=request_data.cj_request_type or "",
                effective_mode=effective_batching_mode,
                iteration_metadata_context=iteration_metadata_context,
            )

            # Propagate reasoning/verbosity overrides into request metadata so that
            # CJ → LPS HTTP payloads can construct LLMConfigOverridesHTTP with the
            # correct reasoning_effort/output_verbosity fields.
            llm_overrides = normalized.llm_config_overrides
            if llm_overrides is not None:
                reasoning_effort = getattr(llm_overrides, "reasoning_effort", None)
                output_verbosity = getattr(llm_overrides, "output_verbosity", None)
                if reasoning_effort is not None or output_verbosity is not None:
                    enriched_metadata_context: dict[str, Any] = dict(metadata_context)
                    if reasoning_effort is not None:
                        enriched_metadata_context.setdefault("reasoning_effort", reasoning_effort)
                    if output_verbosity is not None:
                        enriched_metadata_context.setdefault("output_verbosity", output_verbosity)
                    metadata_context = enriched_metadata_context

            await self._persist_llm_overrides_if_present(
                cj_batch_id=cj_batch_id,
                normalized=normalized,
                correlation_id=correlation_id,
            )

            submission_result = await batch_processor.submit_comparison_batch(
                cj_batch_id=cj_batch_id,
                comparison_tasks=comparison_tasks,
                correlation_id=correlation_id,
                config_overrides=normalized.batch_config_overrides,
                model_override=normalized.model_override,
                temperature_override=normalized.temperature_override,
                max_tokens_override=normalized.max_tokens_override,
                system_prompt_override=normalized.system_prompt_override,
                provider_override=normalized.provider_override,
                metadata_context=metadata_context,
            )

            logger.info(
                "Submitted %s comparisons for async processing",
                submission_result.total_submitted,
                extra={
                    **(
                        {**log_extra_with_mode, "current_iteration": current_iteration}
                        if current_iteration is not None
                        else log_extra_with_mode
                    ),
                    "cj_batch_id": cj_batch_id,
                    "total_submitted": submission_result.total_submitted,
                    "all_submitted": submission_result.all_submitted,
                },
            )

            return True

    async def _prepare_batch_state(
        self,
        *,
        session: AsyncSession,
        cj_batch_id: int,
        normalized: NormalizedComparisonRequest,
        correlation_id: UUID,
    ) -> None:
        await self.batch_repository.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
        )
        metadata_updates = normalized.budget_metadata()
        await merge_batch_processing_metadata(
            session_provider=self.session_provider,
            cj_batch_id=cj_batch_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

    async def _persist_llm_overrides_if_present(
        self,
        *,
        cj_batch_id: int,
        normalized: NormalizedComparisonRequest,
        correlation_id: UUID,
    ) -> None:
        llm_config_overrides = normalized.llm_config_overrides
        if not llm_config_overrides:
            return
        overrides_payload = llm_config_overrides.model_dump(exclude_none=True)
        if not overrides_payload:
            return
        await merge_batch_processing_metadata(
            session_provider=self.session_provider,
            cj_batch_id=cj_batch_id,
            metadata_updates={"llm_overrides": overrides_payload},
            correlation_id=correlation_id,
        )

    async def _get_current_iteration(self, session: AsyncSession, cj_batch_id: int) -> int | None:
        from services.cj_assessment_service.models_db import CJBatchState

        batch_state = await session.get(CJBatchState, cj_batch_id)
        return batch_state.current_iteration if batch_state else None
