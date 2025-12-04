"""Tests for refreshing small-net coverage metadata from repository metrics.

These tests ensure that when coverage progresses across multiple waves,
_derive_small_net_flags and build_small_net_context use repository-derived
coverage metrics to update processing_metadata instead of leaving it stale.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.cj_assessment_service.cj_core_logic.workflow_decision import (
    _derive_small_net_flags,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import CJComparisonRepositoryProtocol


@pytest.mark.asyncio
async def test_small_net_coverage_metadata_refreshed_from_repository_metrics() -> None:
    """Coverage metrics from repo should update stale small-net metadata.

    Starting from metadata that reflects partial coverage (successful_pairs_count
    < max_possible_pairs and unique_coverage_complete=False), the helper should
    consult repository metrics and return effective values that match the
    up-to-date DB view when coverage has progressed.
    """

    settings = Settings()
    settings.MIN_RESAMPLING_NET_SIZE = 10
    settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET = 2

    batch_state = CJBatchState()
    batch_state.batch_upload = CJBatchUpload(
        bos_batch_id="bos-test-coverage-refresh",
        event_correlation_id="00000000-0000-0000-0000-000000000123",
        language="en",
        course_code="eng5",
        expected_essay_count=3,
        status=None,
    )

    # Metadata reflects an earlier, partial view of coverage.
    metadata: dict[str, Any] = {
        "max_possible_pairs": 3,
        "successful_pairs_count": 1,
        "unique_coverage_complete": False,
        "resampling_pass_count": 0,
    }

    comparison_repo = AsyncMock(spec=CJComparisonRepositoryProtocol)
    comparison_repo.get_coverage_metrics_for_batch = AsyncMock(return_value=(3, 3))
    dummy_session = object()

    (
        expected_essay_count,
        is_small_net,
        max_possible_pairs,
        successful_pairs_count,
        unique_coverage_complete,
        resampling_pass_count,
        small_net_resampling_cap,
        small_net_cap_reached,
    ) = await _derive_small_net_flags(
        batch_id=123,
        batch_state=batch_state,
        metadata=metadata,
        settings=settings,
        comparison_repository=comparison_repo,
        session=dummy_session,
        log_extra={},
    )

    assert expected_essay_count == 3
    assert is_small_net is True
    # max_possible_pairs should be preserved at 3.
    assert max_possible_pairs == 3
    # successful_pairs_count should be refreshed to the repository-reported value.
    assert successful_pairs_count == 3
    # With 3 of 3 pairs successful, coverage is complete.
    assert unique_coverage_complete is True
    assert resampling_pass_count == 0
    assert small_net_resampling_cap == settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET
    assert small_net_cap_reached is False
