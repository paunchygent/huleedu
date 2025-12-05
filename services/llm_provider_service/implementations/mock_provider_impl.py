"""Mock LLM provider implementation for testing."""

import asyncio
import hashlib
import math
import random
from typing import Any
from uuid import UUID

from common_core import EssayComparisonWinner, LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import MockMode, Settings
from services.llm_provider_service.exceptions import raise_external_service_error
from services.llm_provider_service.internal_models import LLMProviderResponse
from services.llm_provider_service.protocols import LLMProviderProtocol

logger = create_service_logger("llm_provider_service.mock_provider")


class MockProviderImpl(LLMProviderProtocol):
    """Mock LLM provider for testing without API calls."""

    def __init__(self, settings: Settings, seed: int | None = None, performance_mode: bool = False):
        """Initialize mock provider.

        Args:
            settings: Service settings
            seed: Optional random seed for reproducible tests
            performance_mode: If True, disables error simulation for performance testing
        """
        self.settings = settings
        self.performance_mode = performance_mode
        self.base_seed = seed if seed is not None else settings.MOCK_PROVIDER_SEED
        # Capture mock mode once for quick checks; fall back safely if missing.
        self.mock_mode: MockMode = getattr(settings, "MOCK_MODE", MockMode.DEFAULT)

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        reasoning_effort: str | None = None,
        output_verbosity: str | None = None,
    ) -> LLMProviderResponse:
        """Generate mock comparison result.

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
            HuleEduError: On simulated provider failures
        """
        rng = self._rng(correlation_id)
        resolved_model = model_override or "mock-model-v1"

        await self._apply_latency(rng)
        self._maybe_raise_error(rng, correlation_id, resolved_model)

        full_prompt = user_prompt
        prompt_sha256 = hashlib.sha256(full_prompt.encode("utf-8")).hexdigest()

        winner = self._pick_winner(prompt_sha256)
        confidence = self._pick_confidence(rng)
        justification = self._pick_justification(winner, prompt_sha256)

        prompt_tokens, completion_tokens = self._estimate_tokens(full_prompt, justification)
        total_tokens = prompt_tokens + completion_tokens

        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        cache_metadata = self._cache_metadata(rng, prompt_tokens)

        metadata: dict[str, Any] = {
            "prompt_sha256": prompt_sha256,
            "resolved_provider": "mock",
            "queue_processing_mode": self.settings.QUEUE_PROCESSING_MODE.value,
            **cache_metadata,
            "usage": usage,
        }

        if self.settings.MOCK_STREAMING_METADATA:
            metadata["streaming_simulated"] = True

        response = LLMProviderResponse(
            winner=winner,
            justification=justification,
            confidence=confidence,
            provider=LLMProviderType.MOCK,
            model=model_override or "mock-model-v1",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response={
                "mock_metadata": {
                    "temperature": temperature_override or 0.7,
                    "seed": self.base_seed,
                }
            },
            metadata=metadata,
        )

        logger.debug(
            "Mock provider generated response",
            extra={
                "winner": winner.value,
                "confidence": confidence,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cache_hit": cache_metadata.get("cache_read_input_tokens", 0) > 0,
            },
        )
        return response

    def _is_cj_generic_batch_mode(self) -> bool:
        """Return True when running in cj_generic_batch mock mode."""
        try:
            return self.mock_mode == MockMode.CJ_GENERIC_BATCH
        except Exception:
            # Defensive fallback if settings were partially constructed
            return False

    def _is_eng5_anchor_mode(self) -> bool:
        """Return True when running in ENG5 anchor GPT-5.1 low mock mode."""
        try:
            return self.mock_mode == MockMode.ENG5_ANCHOR_GPT51_LOW
        except Exception:
            # Defensive fallback if settings were partially constructed
            return False

    def _is_eng5_lower5_mode(self) -> bool:
        """Return True when running in ENG5 LOWER5 GPT-5.1 low mock mode."""
        try:
            return self.mock_mode == MockMode.ENG5_LOWER5_GPT51_LOW
        except Exception:
            # Defensive fallback if settings were partially constructed
            return False

    def _rng(self, correlation_id: UUID) -> random.Random:
        """Create a deterministic RNG per request based on seed + correlation ID."""
        combined_seed = hash((self.base_seed, str(correlation_id))) & 0xFFFFFFFF
        return random.Random(combined_seed)

    async def _apply_latency(self, rng: random.Random) -> None:
        base_ms = max(0, self.settings.MOCK_LATENCY_MS)
        jitter_ms = max(0, self.settings.MOCK_LATENCY_JITTER_MS)

        # For ENG5 LOWER5 mode, default to a slightly lower-latency
        # profile than full-anchor while still reflecting real traces
        # when no explicit latency overrides are configured.
        if self._is_eng5_lower5_mode() and base_ms == 0 and jitter_ms == 0:
            base_ms = 1000
            jitter_ms = 1000

        # For ENG5 anchor mode, default to a higher-latency profile that
        # approximates the recorded GPT-5.1 low anchor run when no
        # explicit latency overrides are configured.
        if self._is_eng5_anchor_mode() and base_ms == 0 and jitter_ms == 0:
            base_ms = 1200
            jitter_ms = 800

        if base_ms == 0 and jitter_ms == 0:
            return
        delay_ms = base_ms + rng.uniform(0, jitter_ms)
        await asyncio.sleep(delay_ms / 1000.0)

    def _maybe_raise_error(self, rng: random.Random, correlation_id: UUID, model: str) -> None:
        if (
            self.performance_mode
            or self._is_cj_generic_batch_mode()
            or self._is_eng5_anchor_mode()
            or self._is_eng5_lower5_mode()
        ):
            return

        # Burst mode: if enabled, occasionally force a short run of failures
        burst_len = max(0, self.settings.MOCK_ERROR_BURST_LENGTH)
        if self.settings.MOCK_ERROR_BURST_RATE > 0 and burst_len > 0:
            if rng.random() < self.settings.MOCK_ERROR_BURST_RATE:
                self._raise_mock_error(rng, correlation_id, model)
                return

        if rng.random() < self.settings.MOCK_ERROR_RATE:
            self._raise_mock_error(rng, correlation_id, model)

    def _raise_mock_error(self, rng: random.Random, correlation_id: UUID, model: str) -> None:
        codes = self.settings.MOCK_ERROR_CODES or [500]
        code = rng.choice(codes)
        logger.warning("Mock provider simulating error", extra={"code": code, "model": model})
        raise_external_service_error(
            service="llm_provider_service",
            operation="mock_comparison_generation",
            external_service="mock_provider",
            message="Mock provider simulated error for testing",
            correlation_id=correlation_id,
            status_code=int(code),
            details={
                "provider": "mock",
                "model": model,
                "error_simulation": True,
                "status_code": code,
            },
        )

    def _pick_winner(self, prompt_sha256: str) -> EssayComparisonWinner:
        if self._is_cj_generic_batch_mode():
            # For CJ generic batch mode, keep behaviour pinned: always favour Essay A
            # to mirror winner_counts={"Essay A": N} in reference traces.
            return EssayComparisonWinner.ESSAY_A

        if self._is_eng5_lower5_mode():
            # Bias winner selection to approximate the ENG5 LOWER5
            # GPT-5.1 low distribution (~4/10 Essay A vs 6/10 Essay B)
            # using a stable hash-based mapping over a small net.
            value = int(prompt_sha256[:8], 16)
            return (
                EssayComparisonWinner.ESSAY_A if (value % 10) < 4 else EssayComparisonWinner.ESSAY_B
            )

        if self._is_eng5_anchor_mode():
            # Bias winner selection to approximate the ENG5 full-anchor
            # GPT-5.1 low distribution (35/66 Essay A vs 31/66 Essay B)
            # using a stable hash-based mapping.
            value = int(prompt_sha256[:8], 16)
            return (
                EssayComparisonWinner.ESSAY_A
                if (value % 66) < 35
                else EssayComparisonWinner.ESSAY_B
            )

        value = int(prompt_sha256[:8], 16)
        return EssayComparisonWinner.ESSAY_A if value % 2 == 0 else EssayComparisonWinner.ESSAY_B

    def _pick_confidence(self, rng: random.Random) -> float:
        base = self.settings.MOCK_CONFIDENCE_BASE
        jitter = self.settings.MOCK_CONFIDENCE_JITTER
        val = base + rng.uniform(-jitter, jitter)
        # Confidence in callbacks is 1-5, but LLMProviderResponse expects 0-1
        # Normalize to 0-1 scale to satisfy schema
        normalized = val / 5.0
        return float(min(1.0, max(0.0, round(normalized, 3))))

    def _pick_justification(self, winner: EssayComparisonWinner, prompt_sha256: str) -> str:
        justification_options = {
            EssayComparisonWinner.ESSAY_A: [
                "Essay A demonstrates stronger argumentation and clearer structure.",
                "Essay A provides more compelling evidence and better analysis.",
                "Essay A has superior organization and more persuasive language.",
                "Essay A shows better understanding of the topic with more detailed examples.",
                "Essay A maintains better coherence and has stronger conclusions.",
            ],
            EssayComparisonWinner.ESSAY_B: [
                "Essay B presents a more convincing argument with better supporting evidence.",
                "Essay B demonstrates superior writing quality and clearer expression.",
                "Essay B shows more sophisticated analysis and deeper understanding.",
                "Essay B has better paragraph structure and more effective transitions.",
                "Essay B provides more relevant examples and stronger justification.",
            ],
        }

        options = justification_options[winner]
        idx = int(prompt_sha256[8:12], 16) % len(options)
        return options[idx]

    def _estimate_tokens(self, prompt: str, justification: str) -> tuple[int, int]:
        tokenizer = self.settings.MOCK_TOKENIZER.lower()
        if tokenizer == "tiktoken":
            try:
                import tiktoken  # type: ignore

                enc = tiktoken.get_encoding("cl100k_base")
                prompt_tokens = len(enc.encode(prompt))
                completion_tokens = len(enc.encode(justification)) + 10
                return prompt_tokens, completion_tokens
            except Exception:
                logger.debug("tiktoken unavailable, falling back to simple estimator")

        # Simple estimator: words * multiplier
        def estimate(text: str) -> int:
            words = max(1, len(text.split()))
            return max(1, math.ceil(words * self.settings.MOCK_TOKENS_PER_WORD))

        prompt_tokens = estimate(prompt)
        completion_tokens = estimate(justification) + 10

        # CJ generic batch mode should stay in the lightweight token
        # regime observed in the `cj_lps_roundtrip_mock_20251205`
        # fixture (prompt≈5, completion≈17, total≈22). Keep this
        # behaviour independent of ENG5-specific modes so parity
        # tests can assume small prompts for the generic CJ mode.
        if self._is_cj_generic_batch_mode():
            prompt_tokens = max(prompt_tokens, 5)
            completion_tokens = max(completion_tokens, 17)

        # ENG5 LOWER5 mode uses a moderately high token scale that
        # remains below the full-anchor floor while reflecting LOWER5
        # traces.
        if self._is_eng5_lower5_mode():
            prompt_tokens = max(prompt_tokens, 1000)
            completion_tokens = max(completion_tokens, 30)

        # ENG5 anchor mode uses a higher token scale to approximate
        # large ENG5 prompts and longer justifications observed in
        # the GPT-5.1 low full-anchor traces.
        if self._is_eng5_anchor_mode():
            prompt_tokens = max(prompt_tokens, 1100)
            completion_tokens = max(completion_tokens, 40)

        return prompt_tokens, completion_tokens

    def _cache_metadata(self, rng: random.Random, prompt_tokens: int) -> dict[str, Any]:
        if not self.settings.MOCK_CACHE_ENABLED:
            return {}

        if rng.random() < self.settings.MOCK_CACHE_HIT_RATE:
            return {
                "cache_read_input_tokens": prompt_tokens,
                "cache_creation_input_tokens": 0,
            }

        return {
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": prompt_tokens,
        }
