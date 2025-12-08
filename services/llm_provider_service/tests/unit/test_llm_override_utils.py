"""Unit tests for LLM override helpers in LPS.

Focus: preferred_bundle_size hint parsing semantics.
"""

from __future__ import annotations

from typing import Any

import pytest
from common_core import LLMComparisonRequest

from services.llm_provider_service.implementations.llm_override_utils import (
    get_preferred_bundle_size_hint,
)
from services.llm_provider_service.queue_models import QueuedRequest


def _make_queued_request(metadata: dict[str, Any]) -> QueuedRequest:
    """Helper to construct a minimal QueuedRequest with metadata."""

    request_data = LLMComparisonRequest(
        user_prompt="prompt",
        callback_topic="topic",
        metadata=metadata,
    )
    return QueuedRequest(
        request_data=request_data,
        size_bytes=len(request_data.model_dump_json()),
        callback_topic="topic",
    )


def test_get_preferred_bundle_size_hint_valid_range() -> None:
    """Valid integer in [1, 64] should be returned."""

    request = _make_queued_request({"preferred_bundle_size": 10})

    assert get_preferred_bundle_size_hint(request) == 10


@pytest.mark.parametrize("value", ["10", 10.0, None])
def test_get_preferred_bundle_size_hint_ignores_non_int(value: Any) -> None:
    """Non-integer preferred_bundle_size values should be ignored."""

    request = _make_queued_request({"preferred_bundle_size": value})

    assert get_preferred_bundle_size_hint(request) is None


@pytest.mark.parametrize("value", [0, -1, 65, 100])
def test_get_preferred_bundle_size_hint_ignores_out_of_range(value: int) -> None:
    """Out-of-range integer hints should be ignored."""

    request = _make_queued_request({"preferred_bundle_size": value})

    assert get_preferred_bundle_size_hint(request) is None
