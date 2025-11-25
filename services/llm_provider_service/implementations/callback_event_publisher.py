"""Callback event publishing for LLM request results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from common_core import LLMProviderType
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.prompt_utils import compute_prompt_sha256
from services.llm_provider_service.protocols import LLMEventPublisherProtocol
from services.llm_provider_service.queue_models import QueuedRequest

if TYPE_CHECKING:
    from services.llm_provider_service.config import Settings

logger = create_service_logger("llm_provider_service.callback_publisher")


class CallbackEventPublisher:
    """Constructs and publishes callback events for LLM request results."""

    def __init__(
        self,
        *,
        event_publisher: LLMEventPublisherProtocol,
        settings: Settings,
    ) -> None:
        self.event_publisher = event_publisher
        self.settings = settings

    async def publish_success_event(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        """Publish success callback event for a completed request."""
        try:
            request_meta = dict(request.request_data.metadata or {})
            prompt_hash = result.metadata.get("prompt_sha256") if result.metadata else None
            if prompt_hash:
                request_meta.setdefault("prompt_sha256", prompt_hash)
            provider_metadata = result.metadata or {}
            for key, value in provider_metadata.items():
                if key == "prompt_sha256":
                    continue
                request_meta.setdefault(key, value)

            callback_event = LLMComparisonResultV1(
                request_id=str(request.queue_id),
                correlation_id=request.correlation_id or request.queue_id,
                winner=result.winner,
                justification=result.justification,
                confidence=result.confidence * 4 + 1,
                error_detail=None,
                provider=result.provider,
                model=result.model,
                response_time_ms=result.response_time_ms,
                token_usage=TokenUsage(
                    prompt_tokens=result.token_usage.get("prompt_tokens", 0),
                    completion_tokens=result.token_usage.get("completion_tokens", 0),
                    total_tokens=result.token_usage.get("total_tokens", 0),
                ),
                cost_estimate=result.cost_estimate,
                requested_at=request.queued_at,
                completed_at=datetime.now(timezone.utc),
                trace_id=result.trace_id,
                request_metadata=request_meta,
            )

            envelope = EventEnvelope[LLMComparisonResultV1](
                event_type="LLMComparisonResultV1",
                event_timestamp=datetime.now(timezone.utc),
                source_service="llm_provider_service",
                correlation_id=request.correlation_id or request.queue_id,
                data=callback_event,
            )

            await self.event_publisher.publish_to_topic(
                topic=request.callback_topic,
                envelope=envelope,
            )

            logger.info(
                f"Published success callback event for request {request.queue_id}, "
                f"correlation_id: {request.correlation_id}, "
                f"topic: {request.callback_topic}"
            )

        except Exception as exc:  # pragma: no cover - publish failure should not crash
            logger.error(
                f"Failed to publish callback event for request {request.queue_id}: {exc}, "
                f"correlation_id: {request.correlation_id}",
                exc_info=True,
            )

    async def publish_error_event(self, request: QueuedRequest, error: HuleEduError) -> None:
        """Publish error callback event for a failed request."""
        try:
            fallback_provider = LLMProviderType.OPENAI
            if "provider" in error.error_detail.details:
                try:
                    fallback_provider = LLMProviderType(error.error_detail.details["provider"])
                except ValueError:
                    pass

            request_meta = dict(request.request_data.metadata or {})

            provider_hint = fallback_provider
            overrides = request.request_data.llm_config_overrides
            if overrides and overrides.provider_override:
                provider_hint = overrides.provider_override
            elif "provider" in error.error_detail.details:
                try:
                    provider_hint = LLMProviderType(error.error_detail.details["provider"])
                except ValueError:
                    provider_hint = fallback_provider

            if "prompt_sha256" not in request_meta:
                try:
                    request_meta["prompt_sha256"] = compute_prompt_sha256(
                        provider=provider_hint,
                        user_prompt=request.request_data.user_prompt,
                        prompt_blocks=request.request_data.prompt_blocks,
                    )
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.warning(
                        "Failed to compute prompt hash for error callback",
                        extra={
                            "queue_id": str(request.queue_id),
                            "correlation_id": str(request.correlation_id or ""),
                            "reason": str(exc),
                        },
                    )

            callback_event = LLMComparisonResultV1(
                request_id=str(request.queue_id),
                correlation_id=request.correlation_id or request.queue_id,
                winner=None,
                justification=None,
                confidence=None,
                error_detail=error.error_detail,
                provider=fallback_provider,
                model="unknown",
                response_time_ms=0,
                token_usage=TokenUsage(),
                cost_estimate=0.0,
                requested_at=request.queued_at,
                completed_at=datetime.now(timezone.utc),
                trace_id=None,
                request_metadata=request_meta,
            )

            envelope = EventEnvelope[LLMComparisonResultV1](
                event_type="LLMComparisonResultV1",
                event_timestamp=datetime.now(timezone.utc),
                source_service="llm_provider_service",
                correlation_id=request.correlation_id or request.queue_id,
                data=callback_event,
            )

            await self.event_publisher.publish_to_topic(
                topic=request.callback_topic,
                envelope=envelope,
            )

            logger.info(
                f"Published error callback event for request {request.queue_id}, "
                f"correlation_id: {request.correlation_id}, "
                f"topic: {request.callback_topic}"
            )

        except Exception as exc:  # pragma: no cover - publish failure should not crash
            logger.error(
                f"Failed to publish error callback event for request {request.queue_id}: {exc}, "
                f"correlation_id: {request.correlation_id}",
                exc_info=True,
            )
