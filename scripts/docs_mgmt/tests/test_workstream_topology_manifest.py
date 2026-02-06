"""Tests for workstream topology manifest helpers.

These tests verify parsing and generated-hub block behavior for the
docs-as-code topology contract utilities in
``scripts.docs_mgmt.workstream_topology_manifest``.
"""

from __future__ import annotations

from pathlib import Path

from scripts.docs_mgmt.workstream_topology_manifest import (
    WorkstreamTopology,
    apply_marked_block,
    load_topologies,
    render_marked_block,
    start_marker,
)


def _fake_topology() -> WorkstreamTopology:
    """Create a minimal topology fixture for marker-render tests."""
    return WorkstreamTopology(
        manifest_path=Path("scripts/docs_mgmt/workstream_topology/test.toml"),
        workstream_id="test-stream",
        title="Test Stream",
        hub="docs/reference/ref-test.md",
        runbook="docs/operations/test-runbook.md",
        epic="docs/product/epics/test-epic.md",
        decision="docs/decisions/9999-test.md",
        gate_task="TASKS/assessment/test-gate.md",
        research="docs/research/research-test.md",
        active_tasks=("TASKS/assessment/test-a.md", "TASKS/assessment/test-b.md"),
        review_records=("docs/product/reviews/review-test.md",),
        evidence_roots=("output/essay_scoring",),
    )


def test_load_topologies_contains_essay_scoring_manifest() -> None:
    """Ensure at least one valid topology manifest is loadable."""
    topologies = load_topologies()
    ids = {topology.workstream_id for topology in topologies}
    assert "essay-scoring" in ids
    assert "tasks-lifecycle-v2" in ids


def test_apply_marked_block_appends_when_markers_absent() -> None:
    """Append generated block when a hub does not yet contain topology markers."""
    topology = _fake_topology()
    original = "# Test Hub\n\n## Purpose\n\nExample."
    updated, changed = apply_marked_block(original, topology)
    assert changed is True
    assert start_marker(topology.workstream_id) in updated
    assert render_marked_block(topology) in updated


def test_apply_marked_block_replaces_existing_block() -> None:
    """Replace stale generated content between marker boundaries."""
    topology = _fake_topology()
    stale_content = (
        "# Test Hub\n\n"
        f"{start_marker(topology.workstream_id)}\n"
        "## Topology Contract (Generated)\n\n- stale\n"
        "<!-- END:workstream-topology:test-stream -->\n"
    )
    updated, changed = apply_marked_block(stale_content, topology)
    assert changed is True
    assert "- stale" not in updated
    assert render_marked_block(topology) in updated
