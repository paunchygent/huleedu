"""Unit tests covering prompt hydration metrics exposure."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.cj_assessment_service import metrics


class DummyCounter(SimpleNamespace):
    """Minimal counter implementation for metric exposure tests."""

    def __init__(self) -> None:
        super().__init__(count=0)

    def inc(self) -> None:  # pragma: no cover - not used directly here
        self.count += 1

    def labels(self, **_labels: str) -> "DummyCounter":  # pragma: no cover
        return self


@pytest.mark.parametrize("existing", [{}, None])
def test_get_business_metrics_exposes_prompt_counters(
    existing: dict | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure prompt success/failure counters surface via get_business_metrics."""

    success_counter = DummyCounter()
    failure_counter = DummyCounter()

    base_metrics = {
        "prompt_fetch_success": success_counter,
        "prompt_fetch_failures": failure_counter,
    }

    monkeypatch.setattr(
        metrics, "_metrics", base_metrics if existing is None else {**base_metrics, **existing}
    )

    result = metrics.get_business_metrics()

    assert result["prompt_fetch_success"] is success_counter
    assert result["prompt_fetch_failures"] is failure_counter
