"""Anthropic LLM provider implementation."""

import asyncio
import json
from typing import Any
from uuid import UUID

import aiohttp
from common_core import EssayComparisonWinner, LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_configuration_error,
    raise_external_service_error,
    raise_parsing_error,
    raise_validation_error,
)
from services.llm_provider_service.internal_models import LLMProviderResponse
from services.llm_provider_service.metrics import get_llm_metrics
from services.llm_provider_service.model_manifest import ProviderName
from services.llm_provider_service.prompt_utils import compute_prompt_sha256, render_prompt_blocks
from services.llm_provider_service.protocols import LLMProviderProtocol, LLMRetryManagerProtocol
from services.llm_provider_service.response_validator import validate_and_normalize_response

logger = create_service_logger("llm_provider_service.anthropic_provider")


class AnthropicProviderImpl(LLMProviderProtocol):
    """Anthropic/Claude LLM provider implementation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
    ):
        """Initialize Anthropic provider.

        Args:
            session: HTTP client session
            settings: Service settings
            retry_manager: Retry manager for resilient requests
        """
        self.session = session
        self.settings = settings
        self.retry_manager = retry_manager
        self.api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        self.api_base = settings.ANTHROPIC_BASE_URL or "https://api.anthropic.com/v1"
        self.enable_prompt_caching = getattr(settings, "ENABLE_PROMPT_CACHING", False)
        self.prompt_cache_ttl = getattr(settings, "PROMPT_CACHE_TTL_SECONDS", 3600)
        self.use_extended_ttl_for_service_constants = getattr(
            settings, "USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS", False
        )

        # Log default model configuration from manifest
        try:
            default_config = settings.get_model_from_manifest(ProviderName.ANTHROPIC)
            logger.info(
                "Anthropic provider initialized with manifest configuration",
                extra={
                    "default_model": default_config.model_id,
                    "display_name": default_config.display_name,
                    "api_version": default_config.api_version,
                    "structured_output_method": default_config.structured_output_method.value,
                    "max_tokens": default_config.max_tokens,
                    "context_window": default_config.context_window,
                    "capabilities": default_config.capabilities,
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to load manifest configuration; using hardcoded defaults",
                extra={"error": str(e)},
            )

        self.metrics = get_llm_metrics()

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate LLM comparison response.

        Args:
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID for tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response containing comparison result

        Raises:
            HuleEduError: On any failure to generate comparison
        """
        if not self.api_key:
            raise_configuration_error(
                service="llm_provider_service",
                operation="generate_comparison",
                config_key="ANTHROPIC_API_KEY",
                message="Anthropic API key not configured",
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )

        # Use the complete prompt with essays already embedded
        prompt_text = render_prompt_blocks(prompt_blocks) if prompt_blocks else user_prompt
        if prompt_blocks and prompt_text != user_prompt:
            logger.debug(
                "Prompt text reconstructed from blocks differs from user_prompt; "
                "using block-rendered text for hashing"
            )
        prompt_sha256 = compute_prompt_sha256(
            provider=LLMProviderType.ANTHROPIC,
            user_prompt=prompt_text,
            prompt_blocks=prompt_blocks,
        )

        # Use system prompt from override or default comparison prompt
        system_prompt = system_prompt_override or (
            "You are an LLM comparison engine. Follow the caller-supplied "
            "instructions and ensure your output satisfies the required tool schema."
        )

        # Execute with retry
        try:
            result = await self.retry_manager.with_retry(
                operation=self._make_api_request,
                operation_name="anthropic_api_request",
                system_prompt=system_prompt,
                user_prompt=prompt_text,
                correlation_id=correlation_id,
                prompt_blocks=prompt_blocks,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                prompt_sha256=prompt_sha256,
            )
            # Type assert since retry manager returns Any
            return result  # type: ignore
        except HuleEduError:
            # Preserve existing structured error details from deeper layers
            raise
        except Exception as e:
            error_details = self._build_error_details_from_exception(e)
            http_status = error_details.get("http_status")
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message=f"Anthropic API call failed: {str(e)}",
                correlation_id=correlation_id,
                status_code=http_status
                if isinstance(http_status, int) and http_status > 0
                else None,
                **error_details,
            )

    def _build_error_details_from_exception(self, exc: Exception) -> dict[str, Any]:
        """Construct Anthropic-specific error detail context from an exception.

        This enriches ErrorDetail.details for CJ-facing diagnostics without
        changing the high-level ErrorCode semantics (EXTERNAL_SERVICE_ERROR, etc.).
        """

        details: dict[str, Any] = {"provider": "anthropic"}
        http_status: int = 0
        error_type = "unexpected"
        retryable = False
        error_text: str | None = None

        if isinstance(exc, aiohttp.ClientResponseError):
            http_status = exc.status or 0
            # When we construct ClientResponseError ourselves we set message to the raw body
            error_text = getattr(exc, "message", None)
            if http_status == 429:
                error_type = "rate_limit"
                retryable = True
            elif http_status == 529:
                error_type = "overloaded"
                retryable = True
            elif http_status == 401:
                error_type = "authentication"
            elif http_status >= 500:
                error_type = "server_error"
                retryable = http_status in {500, 502, 503, 504}
            elif http_status >= 400:
                error_type = "client_error"
        elif isinstance(exc, aiohttp.ClientError):
            http_status = 0
            error_type = "connection_error"
            retryable = True
            error_text = str(exc)
        else:
            http_status = 0
            error_type = "unexpected"
            retryable = False
            error_text = str(exc)

        provider_error_code = "unknown"
        provider_error_type: str | None = None
        provider_error_message: str | None = None
        if error_text:
            code, err_type, msg = self._parse_anthropic_error_json(error_text)
            if code:
                provider_error_code = code
            provider_error_type = err_type
            provider_error_message = msg

        if provider_error_type == "overloaded_error":
            error_type = "overloaded"
            retryable = True

        details.update(
            {
                "http_status": http_status,
                "error_type": error_type,
                "retryable": retryable,
                "provider_error_code": provider_error_code,
            }
        )
        if provider_error_type:
            details["provider_error_type"] = provider_error_type
        if provider_error_message:
            details["provider_error_message"] = provider_error_message[:500]
        return details

    @staticmethod
    def _parse_anthropic_error_json(raw: str) -> tuple[str | None, str | None, str | None]:
        """Best-effort parsing of Anthropic JSON error payloads.

        Expected shape: {"error": {"type": "...", "code": "...", "message": "..."}}.
        Returns (code, type, message) when available, otherwise (None, None, None).
        """

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, None, None
        if not isinstance(data, dict):
            return None, None, None
        err = data.get("error")
        if not isinstance(err, dict):
            return None, None, None

        code_val = err.get("code") or err.get("type")
        code = code_val if isinstance(code_val, str) else None
        err_type = err.get("type") if isinstance(err.get("type"), str) else None
        msg = err.get("message") if isinstance(err.get("message"), str) else None
        return code, err_type, msg

    def _record_prompt_cache_metrics(self, *, model: str, usage: dict[str, Any] | None) -> None:
        """Record prompt cache hit/miss and token utilization metrics when enabled."""

        if not self.enable_prompt_caching or not self.metrics or not isinstance(usage, dict):
            return

        cache_events = self.metrics.get("llm_provider_prompt_cache_events_total")
        cache_tokens = self.metrics.get("llm_provider_prompt_cache_tokens_total")

        cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
        cache_write_tokens = int(usage.get("cache_creation_input_tokens") or 0)

        if cache_read_tokens > 0:
            result = "hit"
        elif cache_write_tokens > 0:
            result = "miss"
        else:
            result = "bypass"

        if cache_events is not None:
            cache_events.labels(provider="anthropic", model=model, result=result).inc()

        if cache_tokens is not None:
            if cache_read_tokens > 0:
                cache_tokens.labels(provider="anthropic", model=model, direction="read").inc(
                    cache_read_tokens
                )
            if cache_write_tokens > 0:
                cache_tokens.labels(provider="anthropic", model=model, direction="write").inc(
                    cache_write_tokens
                )

    def _normalize_ttl_value(self, ttl_hint: Any, correlation_id: UUID) -> str:
        """Normalize TTL to Anthropic-supported string values ('5m' or '1h')."""

        if ttl_hint is None:
            return "5m"

        if isinstance(ttl_hint, (int, float)):
            return "1h" if ttl_hint >= 3600 else "5m"

        ttl_str = str(ttl_hint).lower().strip()
        if ttl_str in {"5m", "300", "300s"}:
            return "5m"
        if ttl_str in {"1h", "60m", "3600", "3600s"}:
            return "1h"

        raise_validation_error(
            service="llm_provider_service",
            operation="anthropic_build_payload",
            field="ttl",
            message=f"Invalid cache TTL value: {ttl_hint}",
            correlation_id=correlation_id,
            details={"provider": "anthropic", "ttl_value": str(ttl_hint)},
        )

    def _select_cache_ttl(
        self, prompt_blocks: list[dict[str, Any]] | None, correlation_id: UUID
    ) -> str:
        """Select cache TTL based on prompt blocks or service defaults."""

        if prompt_blocks:
            for block in prompt_blocks:
                if (
                    block.get("cacheable")
                    and self._normalize_ttl_value(block.get("ttl"), correlation_id) == "1h"
                ):
                    return "1h"
            return "5m"

        if self.use_extended_ttl_for_service_constants and self.prompt_cache_ttl >= 3600:
            return "1h"

        return "5m"

    def _validate_prompt_block_order(
        self, prompt_blocks: list[dict[str, Any]], correlation_id: UUID, model: str
    ) -> None:
        """Ensure prompt blocks respect Anthropic TTL ordering (1h before 5m)."""

        seen_five_min = False
        for idx, block in enumerate(prompt_blocks):
            if not block.get("cacheable"):
                continue

            ttl_value = self._normalize_ttl_value(block.get("ttl"), correlation_id)
            if ttl_value == "5m":
                seen_five_min = True
            elif ttl_value == "1h" and seen_five_min:
                self._record_ttl_violation(model=model, stage="incoming_blocks")
                raise_validation_error(
                    service="llm_provider_service",
                    operation="anthropic_build_payload",
                    field="prompt_blocks",
                    message="1h TTL block must precede 5m TTL blocks",
                    correlation_id=correlation_id,
                    details={"provider": "anthropic", "block_index": idx},
                )

    def _record_ttl_violation(self, *, model: str, stage: str) -> None:
        """Increment TTL violation counter when available."""

        if not self.metrics:
            return

        ttl_metric = self.metrics.get("llm_provider_prompt_ttl_violations_total")
        if ttl_metric is None:
            return

        ttl_metric.labels(provider="anthropic", model=model or "unknown", stage=stage).inc()

    def _validate_cache_ttl_ordering(
        self, blocks: list[dict[str, Any]], correlation_id: UUID, *, model: str, stage: str
    ) -> None:
        """Validate cache_control TTL ordering within a constructed message list."""

        seen_five_min = False
        for idx, block in enumerate(blocks):
            cache_control = block.get("cache_control")
            if not cache_control:
                continue
            ttl_value = self._normalize_ttl_value(cache_control.get("ttl"), correlation_id)
            if ttl_value == "5m":
                seen_five_min = True
            elif ttl_value == "1h" and seen_five_min:
                self._record_ttl_violation(model=model, stage=stage)
                raise_validation_error(
                    service="llm_provider_service",
                    operation="anthropic_build_payload",
                    field="prompt_blocks",
                    message="Constructed payload violates TTL ordering (1h after 5m)",
                    correlation_id=correlation_id,
                    details={"provider": "anthropic", "block_index": idx},
                )

    def _build_message_content(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        prompt_blocks: list[dict[str, Any]] | None,
        cache_ttl: str,
        correlation_id: UUID,
        model: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Construct system/user content blocks honoring cache settings and ordering."""

        system_content: list[dict[str, Any]] = []
        user_content: list[dict[str, Any]] = []

        system_block: dict[str, Any] = {"type": "text", "text": system_prompt}
        if self.enable_prompt_caching:
            system_block["cache_control"] = {"type": "ephemeral", "ttl": cache_ttl}
        system_content.append(system_block)

        if prompt_blocks:
            self._validate_prompt_block_order(prompt_blocks, correlation_id, model)

            for block in prompt_blocks:
                block_target = str(block.get("target") or "user_content")
                ttl_value = self._normalize_ttl_value(block.get("ttl"), correlation_id)
                payload_block: dict[str, Any] = {
                    "type": "text",
                    "text": block.get("content", ""),
                }
                if block.get("cacheable") and self.enable_prompt_caching:
                    payload_block["cache_control"] = {"type": "ephemeral", "ttl": ttl_value}

                if block_target == "system":
                    system_content.append(payload_block)
                else:
                    user_content.append(payload_block)
        else:
            user_content.append({"type": "text", "text": user_prompt})

        if not user_content:
            user_content.append({"type": "text", "text": user_prompt})

        self._validate_cache_ttl_ordering(
            system_content, correlation_id, model=model, stage="system_blocks"
        )
        self._validate_cache_ttl_ordering(
            user_content, correlation_id, model=model, stage="user_blocks"
        )

        return system_content, user_content

    async def _make_api_request(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        prompt_sha256: str | None = None,
    ) -> LLMProviderResponse:
        """Make API request to Anthropic.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt with essays
            correlation_id: Request correlation ID for tracing
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response

        Raises:
            HuleEduError: On any failure to make API request
        """
        endpoint = f"{self.api_base}/messages"

        # Determine model and get manifest configuration
        model = model_override or self.settings.ANTHROPIC_DEFAULT_MODEL

        # Get API version and configuration from manifest
        api_version = "2023-06-01"  # Fallback
        try:
            model_config = self.settings.get_model_from_manifest(ProviderName.ANTHROPIC, model)
            api_version = model_config.api_version

            # Log model selection
            logger.info(
                "Using Anthropic model from manifest",
                extra={
                    "model_id": model_config.model_id,
                    "display_name": model_config.display_name,
                    "api_version": api_version,
                    "using_override": model_override is not None,
                    "correlation_id": str(correlation_id),
                },
            )
        except ValueError:
            # Model not in manifest - log warning and use fallback
            logger.warning(
                "Model not found in manifest; using hardcoded API version",
                extra={
                    "model": model,
                    "fallback_api_version": api_version,
                    "correlation_id": str(correlation_id),
                },
            )

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": api_version,
            "content-type": "application/json",
        }

        temperature = (
            temperature_override
            if temperature_override is not None
            else self.settings.LLM_DEFAULT_TEMPERATURE
        )
        max_tokens = max_tokens_override or self.settings.LLM_DEFAULT_MAX_TOKENS

        # Define tool for structured comparison response
        tools = [
            {
                "name": "comparison_result",
                "description": "Essay comparison result",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "winner": {"type": "string", "enum": ["Essay A", "Essay B"]},
                        "justification": {
                            "type": "string",
                            "maxLength": 50,
                            "description": "Brief explanation (max 50 chars)",
                        },
                        "confidence": {"type": "number", "minimum": 1, "maximum": 5},
                    },
                    "required": ["winner", "justification", "confidence"],
                },
            }
        ]

        cache_ttl = self._select_cache_ttl(prompt_blocks, correlation_id)
        if self.enable_prompt_caching:
            tools[0]["cache_control"] = {"type": "ephemeral", "ttl": cache_ttl}

        system_blocks, user_message_content = self._build_message_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_blocks=prompt_blocks,
            cache_ttl=cache_ttl,
            correlation_id=correlation_id,
            model=model,
        )

        metadata: dict[str, Any] = {
            "correlation_id": str(correlation_id),
            "provider": "anthropic",
        }

        if prompt_sha256:
            metadata["prompt_sha256"] = prompt_sha256

        payload = {
            "model": model,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user_message_content}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": {"type": "tool", "name": "comparison_result"},
            "metadata": metadata,
        }

        response_text = await self._perform_http_request_with_metrics(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            correlation_id=correlation_id,
            model=model,
        )

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse Anthropic response as JSON: {e}",
                extra={"response_text": response_text[:500]},
            )
            raise_parsing_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                parse_target="json",
                message=f"Failed to parse Anthropic response: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )

        # Log the structure for debugging
        logger.debug(
            "Anthropic response structure",
            extra={
                "has_content": "content" in response_data,
                "content_type": type(response_data.get("content")).__name__,
                "content_length": len(response_data.get("content", []))
                if isinstance(response_data.get("content"), list)
                else 0,
            },
        )

        stop_reason = response_data.get("stop_reason")
        if stop_reason == "max_tokens":
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message="Anthropic truncated response due to max_tokens limit",
                correlation_id=correlation_id,
                details={
                    "provider": "anthropic",
                    "stop_reason": stop_reason,
                    "max_tokens": max_tokens,
                },
            )

        # Extract tool use from Anthropic response
        tool_result = None
        if isinstance(response_data.get("content"), list):
            for block in response_data["content"]:
                if block.get("type") == "tool_use" and block.get("name") == "comparison_result":
                    tool_result = block.get("input", {})
                    break

        if tool_result:
            try:
                # Validate and normalize response using centralized validator
                validated_response = validate_and_normalize_response(
                    tool_result, provider="anthropic", correlation_id=correlation_id
                )

                # Use validated response directly
                # (already in assessment domain language)

                # Convert winner string to enum value
                if validated_response.winner == "Essay A":
                    winner = EssayComparisonWinner.ESSAY_A
                elif validated_response.winner == "Essay B":
                    winner = EssayComparisonWinner.ESSAY_B
                else:
                    winner = EssayComparisonWinner.ERROR

                # Get token usage
                usage = response_data.get("usage", {})
                self._record_prompt_cache_metrics(model=model, usage=usage)
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                total_tokens = prompt_tokens + completion_tokens

                # Convert confidence from 1-5 scale to 0-1 scale for internal model
                confidence_normalized = (validated_response.confidence - 1.0) / 4.0

                # Create response model
                response_metadata: dict[str, Any] = {}
                if prompt_sha256:
                    response_metadata["prompt_sha256"] = prompt_sha256
                if usage:
                    response_metadata["usage"] = usage
                    if usage.get("cache_read_input_tokens") is not None:
                        response_metadata["cache_read_input_tokens"] = usage.get(
                            "cache_read_input_tokens"
                        )
                    if usage.get("cache_creation_input_tokens") is not None:
                        response_metadata["cache_creation_input_tokens"] = usage.get(
                            "cache_creation_input_tokens"
                        )

                response_model = LLMProviderResponse(
                    winner=winner,
                    justification=validated_response.justification,
                    confidence=confidence_normalized,
                    provider=LLMProviderType.ANTHROPIC,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    raw_response=response_data,
                    metadata=response_metadata,
                )

                return response_model

            except (ValueError, KeyError, TypeError) as e:
                error_msg = f"Failed to parse Anthropic tool response: {str(e)}"
                logger.error(error_msg, extra={"tool_result": str(tool_result)[:500]})
                raise_parsing_error(
                    service="llm_provider_service",
                    operation="anthropic_api_request",
                    parse_target="tool_response",
                    message=error_msg,
                    correlation_id=correlation_id,
                    details={"provider": "anthropic"},
                )
        else:
            # Log the full response for debugging
            logger.error(
                "No tool use found in Anthropic response",
                extra={"response_data": str(response_data)[:1000]},
            )

            if self.metrics:
                # error_type values:
                # - rate_limit, authentication, server_error, client_error
                # - connection_error, unexpected (non-HTTP failures)
                # - invalid_response (HTTP 200 with malformed or missing tool payload)
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="invalid_response",
                        http_status_code="200",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="invalid_response",
                    ).inc()

            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message="No tool use found in Anthropic response",
                correlation_id=correlation_id,
                details={
                    "provider": "anthropic",
                    "http_status": 200,
                    "error_type": "invalid_response",
                    "retryable": False,
                    "provider_error_code": "invalid_response",
                },
            )

    async def _perform_http_request_with_metrics(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        correlation_id: UUID,
        model: str,
    ) -> str:
        """Make a request to the Anthropic API and record error diagnostics."""

        try:
            async with self.session.post(
                endpoint,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    return await response.text()

                error_text = await response.text()
                error_msg = f"Anthropic API error: {response.status} - {error_text}"

                # Record API error metrics. error_type semantics:
                # - rate_limit, authentication, server_error, client_error
                # - connection_error, unexpected (non-HTTP failures)
                # - invalid_response (HTTP 200 with malformed body, recorded separately)
                error_type = "unknown"
                retry_after_header = response.headers.get("retry-after")
                if response.status == 429:
                    error_type = "rate_limit"
                    try:
                        retry_after_seconds = int(float(retry_after_header or "0"))
                        bounded_retry_after = min(retry_after_seconds, 5)
                        if bounded_retry_after > 0:
                            await asyncio.sleep(bounded_retry_after)
                    except Exception:
                        pass
                elif response.status == 529:
                    error_type = "overloaded"
                elif response.status == 401:
                    error_type = "authentication"
                elif response.status >= 500:
                    error_type = "server_error"
                elif response.status >= 400:
                    error_type = "client_error"

                if self.metrics:
                    api_errors = self.metrics.get("llm_provider_api_errors_total")
                    provider_errors = self.metrics.get("llm_provider_errors_total")
                    if api_errors is not None:
                        api_errors.labels(
                            provider="anthropic",
                            error_type=error_type,
                            http_status_code=str(response.status),
                        ).inc()
                    if provider_errors is not None:
                        provider_errors.labels(
                            provider="anthropic",
                            model=model,
                            error_type=error_type,
                        ).inc()

                # Log detailed error info
                log_extra = {
                    "status_code": response.status,
                    "error_text": error_text[:1000],
                    "correlation_id": str(correlation_id),
                    "provider": "anthropic",
                }

                # Capture rate limit headers if present
                for header in ["x-ratelimit-remaining", "x-ratelimit-reset", "retry-after"]:
                    if val := response.headers.get(header):
                        log_extra[header] = val

                logger.error(f"Anthropic API failure: {response.status}", extra=log_extra)

                # For HTTP error statuses, raise ClientResponseError so the retry
                # manager can apply its policies based on the status code.
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=(),
                    status=response.status,
                    message=error_text,
                    headers=response.headers,
                )

        except aiohttp.ClientResponseError:
            # Will be retried by retry manager
            raise
        except aiohttp.ClientError:
            # Connection errors, timeouts, etc.
            if self.metrics:
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="connection_error",
                        http_status_code="0",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="connection_error",
                    ).inc()
            raise
        except Exception as e:
            # Unexpected errors
            if self.metrics:
                api_errors = self.metrics.get("llm_provider_api_errors_total")
                provider_errors = self.metrics.get("llm_provider_errors_total")
                if api_errors is not None:
                    api_errors.labels(
                        provider="anthropic",
                        error_type="unexpected",
                        http_status_code="0",
                    ).inc()
                if provider_errors is not None:
                    provider_errors.labels(
                        provider="anthropic",
                        model=model,
                        error_type="unexpected",
                    ).inc()

            error_msg = f"Unexpected error calling Anthropic API: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise_external_service_error(
                service="llm_provider_service",
                operation="anthropic_api_request",
                external_service="anthropic_api",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": "anthropic"},
            )
