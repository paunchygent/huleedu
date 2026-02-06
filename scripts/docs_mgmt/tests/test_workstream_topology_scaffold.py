"""Tests for the workstream topology scaffold command.

These tests focus on deterministic scaffold behavior and strict invariant
checks in ``scripts.docs_mgmt.workstream_topology_scaffold``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_mgmt.workstream_topology_manifest import TopologyManifestError, WorkstreamTopology
from scripts.docs_mgmt.workstream_topology_scaffold import (
    build_manifest_text,
    scaffold_workstream_topology,
)


def _touch_file(base_dir: Path, rel_path: str, content: str = "# doc\n") -> None:
    """Create one file under a temporary repo root.

    Args:
        base_dir: Temporary repository root.
        rel_path: Repo-relative file path.
        content: File content to write.
    """
    path = base_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_manifest_text_has_deterministic_sections() -> None:
    """Ensure manifest rendering emits required sections in stable order."""
    topology = WorkstreamTopology(
        manifest_path=Path("scripts/docs_mgmt/workstream_topology/example.toml"),
        workstream_id="example-stream",
        title="Example Stream",
        hub="docs/reference/ref-example.md",
        runbook="docs/operations/example.md",
        epic="docs/product/epics/example.md",
        decision="docs/decisions/0001-example.md",
        gate_task="TASKS/architecture/example.md",
        research="docs/research/research-example.md",
        active_tasks=("TASKS/architecture/example.md",),
        review_records=("docs/product/reviews/review-example.md",),
        evidence_roots=("output/example",),
    )
    text = build_manifest_text(topology)
    assert text.startswith("[workstream]")
    assert "\n[canonical]\n" in text
    assert "\n[links]\n" in text
    assert 'id = "example-stream"' in text
    assert 'gate_task = "TASKS/architecture/example.md"' in text


def test_scaffold_creates_manifest_and_hub_markers(tmp_path: Path) -> None:
    """Create a manifest and verify generated markers are written to hub."""
    root_dir = tmp_path / "repo"
    manifest_dir = root_dir / "scripts" / "docs_mgmt" / "workstream_topology"
    evidence_dir = root_dir / "output" / "example"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _touch_file(root_dir, "docs/reference/ref-example.md", "# Example Hub\n")
    _touch_file(root_dir, "docs/reference/ref-example-runbook.md")
    _touch_file(root_dir, "docs/product/epics/example-epic.md")
    _touch_file(root_dir, "docs/decisions/0001-example.md")
    _touch_file(root_dir, "TASKS/architecture/example-gate.md")
    _touch_file(root_dir, "docs/research/research-example.md")
    _touch_file(root_dir, "TASKS/architecture/example-track.md")
    _touch_file(root_dir, "docs/product/reviews/review-example.md")

    result = scaffold_workstream_topology(
        root_dir=root_dir,
        manifest_dir=manifest_dir,
        workstream_id="example-stream",
        title="Example Stream",
        hub="docs/reference/ref-example.md",
        runbook="docs/reference/ref-example-runbook.md",
        epic="docs/product/epics/example-epic.md",
        decision="docs/decisions/0001-example.md",
        gate_task="TASKS/architecture/example-gate.md",
        research="docs/research/research-example.md",
        active_tasks=("TASKS/architecture/example-track.md",),
        review_records=("docs/product/reviews/review-example.md",),
        evidence_roots=("output/example",),
        force=False,
    )

    assert result.manifest_path.exists()
    hub_content = (root_dir / "docs/reference/ref-example.md").read_text(encoding="utf-8")
    assert "<!-- BEGIN:workstream-topology:example-stream -->" in hub_content
    assert "<!-- END:workstream-topology:example-stream -->" in hub_content


def test_scaffold_rejects_duplicate_list_entries(tmp_path: Path) -> None:
    """Reject duplicate repeatable args to prevent ambiguous topology shape."""
    root_dir = tmp_path / "repo"
    manifest_dir = root_dir / "scripts" / "docs_mgmt" / "workstream_topology"
    evidence_dir = root_dir / "output" / "example"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _touch_file(root_dir, "docs/reference/ref-example.md", "# Example Hub\n")
    _touch_file(root_dir, "docs/reference/ref-example-runbook.md")
    _touch_file(root_dir, "docs/product/epics/example-epic.md")
    _touch_file(root_dir, "docs/decisions/0001-example.md")
    _touch_file(root_dir, "TASKS/architecture/example-gate.md")
    _touch_file(root_dir, "docs/research/research-example.md")
    _touch_file(root_dir, "TASKS/architecture/example-track.md")
    _touch_file(root_dir, "docs/product/reviews/review-example.md")

    with pytest.raises(TopologyManifestError):
        scaffold_workstream_topology(
            root_dir=root_dir,
            manifest_dir=manifest_dir,
            workstream_id="example-stream",
            title="Example Stream",
            hub="docs/reference/ref-example.md",
            runbook="docs/reference/ref-example-runbook.md",
            epic="docs/product/epics/example-epic.md",
            decision="docs/decisions/0001-example.md",
            gate_task="TASKS/architecture/example-gate.md",
            research="docs/research/research-example.md",
            active_tasks=(
                "TASKS/architecture/example-track.md",
                "TASKS/architecture/example-track.md",
            ),
            review_records=("docs/product/reviews/review-example.md",),
            evidence_roots=("output/example",),
            force=False,
        )
