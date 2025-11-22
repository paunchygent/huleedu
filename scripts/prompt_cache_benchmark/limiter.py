from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable


class DualBucketRateLimiter:
    """Async token bucket with independent request and token budgets."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        tokens_per_minute: int,
        time_fn: Callable[[], float] | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.requests_capacity = max(requests_per_minute, 1)
        # Treat <=0 as unlimited token budget
        self.tokens_capacity = max(tokens_per_minute, 0)

        self._time = time_fn or time.monotonic
        self._sleep = sleep_func or asyncio.sleep

        self._req_tokens = float(self.requests_capacity)
        self._tok_tokens = float(self.tokens_capacity)
        self._last_refill = self._time()
        self._lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return

        req_rate = self.requests_capacity / 60.0
        tok_rate = self.tokens_capacity / 60.0 if self.tokens_capacity else 0.0

        self._req_tokens = min(float(self.requests_capacity), self._req_tokens + elapsed * req_rate)
        if self.tokens_capacity:
            self._tok_tokens = min(
                float(self.tokens_capacity), self._tok_tokens + elapsed * tok_rate
            )

        self._last_refill = now

    async def acquire(self, *, estimated_tokens: int = 0) -> None:
        """Block until capacity is available, then debit budgets."""

        tokens_needed = max(estimated_tokens, 0)
        if self.tokens_capacity:
            tokens_needed = min(tokens_needed, self.tokens_capacity)
        else:
            tokens_needed = 0

        while True:
            async with self._lock:
                now = self._time()
                self._refill(now)

                req_shortfall = max(1.0 - self._req_tokens, 0.0)
                tok_shortfall = max(tokens_needed - self._tok_tokens, 0.0) if tokens_needed else 0.0

                if req_shortfall <= 0 and tok_shortfall <= 0:
                    self._req_tokens -= 1.0
                    if tokens_needed:
                        self._tok_tokens -= tokens_needed
                    return

                req_wait = (
                    req_shortfall / (self.requests_capacity / 60.0) if req_shortfall > 0 else 0.0
                )
                tok_wait = (
                    tok_shortfall / (self.tokens_capacity / 60.0)
                    if tok_shortfall > 0 and self.tokens_capacity
                    else 0.0
                )

                wait_time = max(req_wait, tok_wait, 0.0)

            await self._sleep(wait_time)
