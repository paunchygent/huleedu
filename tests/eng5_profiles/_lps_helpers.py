"""Shared helpers for ENG5 mock profile tests.

Extracted to avoid duplication across test implementations.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import aiohttp
import pytest


async def get_lps_mock_mode(base_url: str) -> dict[str, Any]:
    """Query LPS /admin/mock-mode with retry logic for transient connection errors.

    Args:
        base_url: LPS service base URL (e.g., http://localhost:4002)

    Returns:
        Mock mode configuration dict from LPS

    Raises:
        aiohttp.ClientConnectionError: After 3 failed attempts
        pytest.skip: If endpoint returns non-200 status
    """
    admin_url = f"{base_url}/admin/mock-mode"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    admin_url,
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    if resp.status != 200:
                        pytest.skip(
                            "/admin/mock-mode not available on LPS; "
                            "ensure dev config exposes this endpoint"
                        )
                    data = await resp.json()
                    return cast(dict[str, Any], data)
        except aiohttp.ClientConnectionError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))

    raise RuntimeError("Unreachable")
