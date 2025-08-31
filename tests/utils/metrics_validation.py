"""
Metrics Validation Utilities

Helpers to parse Prometheus text and validate that key counters and
histograms for proxy/downstream calls are present and incremented.

Identity values MUST NOT be used as metric labels.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Tuple


SAMPLE_RE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>[^}]*)\}\s+(?P<value>[-+]?[0-9]*\.?[0-9]+(e[-+]?\d+)?)$")


def parse_labels(labels_str: str) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for part in labels_str.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        labels[k.strip()] = v.strip().strip('"')
    return labels


def iter_metric_samples(metrics_text: str) -> Iterable[Tuple[str, Dict[str, str], float]]:
    for line in metrics_text.splitlines():
        m = SAMPLE_RE.match(line.strip())
        if not m:
            continue
        name = m.group("name")
        labels = parse_labels(m.group("labels"))
        value = float(m.group("value"))
        yield name, labels, value


def find_metric_values(
    metrics_text: str, metric_name: str, labels_subset: Optional[Dict[str, str]] = None
) -> list[float]:
    values: list[float] = []
    for name, labels, value in iter_metric_samples(metrics_text):
        if name != metric_name:
            continue
        if labels_subset:
            # Check that all requested labels are present and equal
            if any(labels.get(k) != v for k, v in labels_subset.items()):
                continue
        values.append(value)
    return values


def assert_metric_incremented(
    before_text: str,
    after_text: str,
    metric_name: str,
    labels_subset: Optional[Dict[str, str]] = None,
) -> None:
    """
    Assert that a counter/gauge value increased between two metric snapshots.
    """
    before_vals = find_metric_values(before_text, metric_name, labels_subset)
    after_vals = find_metric_values(after_text, metric_name, labels_subset)
    if not after_vals:
        raise AssertionError(f"Metric '{metric_name}' with labels {labels_subset} not found in 'after' snapshot")
    if not before_vals:
        # If not present before, require non-zero after
        if max(after_vals) <= 0:
            raise AssertionError(
                f"Metric '{metric_name}' did not increase; 'before' missing, 'after' max={max(after_vals)}"
            )
        return
    if max(after_vals) <= max(before_vals):
        raise AssertionError(
            f"Metric '{metric_name}' did not increase: before={max(before_vals)} after={max(after_vals)}"
        )

