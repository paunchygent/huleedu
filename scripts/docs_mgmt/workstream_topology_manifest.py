"""Workstream topology helpers for docs-as-code governance.

This module is the shared contract layer for:
- ``scripts.docs_mgmt.validate_workstream_topology`` (policy checks), and
- ``scripts.docs_mgmt.render_workstream_hubs`` (generated hub navigation blocks).

Manifests define canonical workstream navigation in TOML, while this module handles
loading, validation, and hub block rendering logic.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_DIR = ROOT / "scripts" / "docs_mgmt" / "workstream_topology"


class TopologyManifestError(ValueError):
    """Raised when a workstream topology manifest is invalid."""


@dataclass(frozen=True)
class WorkstreamTopology:
    """Typed representation of one workstream topology manifest.

    Args:
        manifest_path: Absolute path to the TOML manifest.
        workstream_id: Stable workstream slug used in hub marker comments.
        title: Human-readable workstream title.
        hub: Canonical reference hub path.
        runbook: Canonical operations/runbook doc path.
        epic: Canonical epic doc path.
        decision: Canonical decision (ADR) path.
        gate_task: Canonical decision-gate task path.
        research: Canonical research note path.
        active_tasks: Active execution task paths for this workstream.
        review_records: Review-record doc paths tied to active tracks.
        evidence_roots: Evidence root directories for runs/reports.
    """

    manifest_path: Path
    workstream_id: str
    title: str
    hub: str
    runbook: str
    epic: str
    decision: str
    gate_task: str
    research: str
    active_tasks: tuple[str, ...]
    review_records: tuple[str, ...]
    evidence_roots: tuple[str, ...]

    @property
    def manifest_relpath(self) -> str:
        """Return the repo-relative manifest path."""
        try:
            return self.manifest_path.relative_to(ROOT).as_posix()
        except ValueError:
            return self.manifest_path.as_posix()

    @property
    def all_markdown_paths(self) -> tuple[str, ...]:
        """Return all Markdown paths referenced by the manifest."""
        return (
            self.hub,
            self.runbook,
            self.epic,
            self.decision,
            self.gate_task,
            self.research,
            *self.active_tasks,
            *self.review_records,
        )

    @property
    def backlink_required_paths(self) -> tuple[str, ...]:
        """Return docs/tasks that must include a backlink to the hub."""
        return (
            self.decision,
            self.gate_task,
            self.research,
            *self.active_tasks,
            *self.review_records,
        )


def is_repo_relative(path_str: str) -> bool:
    """Check if a path is safe repo-relative (no absolute path and no ``..``).

    Args:
        path_str: Candidate repository-relative path.

    Returns:
        ``True`` when the path is non-empty, relative, and does not traverse up.
    """
    if not path_str.strip():
        return False
    candidate = Path(path_str)
    return not candidate.is_absolute() and ".." not in candidate.parts


def resolve_repo_path(path_str: str) -> Path:
    """Resolve a repository-relative path to an absolute path.

    Args:
        path_str: Repository-relative path.

    Returns:
        Absolute path anchored at repository root.
    """
    return ROOT / Path(path_str)


def start_marker(workstream_id: str) -> str:
    """Build the start marker used for generated hub topology blocks."""
    return f"<!-- BEGIN:workstream-topology:{workstream_id} -->"


def end_marker(workstream_id: str) -> str:
    """Build the end marker used for generated hub topology blocks."""
    return f"<!-- END:workstream-topology:{workstream_id} -->"


def render_topology_section(topology: WorkstreamTopology) -> str:
    """Render the generated Markdown section for one workstream hub.

    Args:
        topology: Parsed topology manifest.

    Returns:
        Markdown text for the generated section.
    """
    lines = [
        "## Topology Contract (Generated)",
        "",
        f"- Manifest: `{topology.manifest_relpath}`",
        "- Canonical chain:",
        f"  - Runbook: `{topology.runbook}`",
        f"  - Epic: `{topology.epic}`",
        f"  - Decision: `{topology.decision}`",
        f"  - Decision gate task: `{topology.gate_task}`",
        f"  - Research: `{topology.research}`",
        "- Active tracks:",
    ]
    for task_path in topology.active_tasks:
        lines.append(f"  - `{task_path}`")
    lines.append("- Review records:")
    for review_path in topology.review_records:
        lines.append(f"  - `{review_path}`")
    lines.append("- Evidence roots:")
    for evidence_root in topology.evidence_roots:
        lines.append(f"  - `{evidence_root}`")
    return "\n".join(lines)


def render_marked_block(topology: WorkstreamTopology) -> str:
    """Render the generated section wrapped by topology markers.

    Args:
        topology: Parsed topology manifest.

    Returns:
        Marker-wrapped Markdown block.
    """
    block = render_topology_section(topology).strip()
    return "\n".join(
        [
            start_marker(topology.workstream_id),
            block,
            end_marker(topology.workstream_id),
        ]
    )


def apply_marked_block(content: str, topology: WorkstreamTopology) -> tuple[str, bool]:
    """Apply (or append) a generated topology block to a hub document.

    Args:
        content: Existing hub Markdown content.
        topology: Parsed topology manifest.

    Returns:
        Tuple ``(new_content, changed)`` where ``changed`` reports whether content changed.

    Raises:
        TopologyManifestError: If marker pairs are malformed.
    """
    start = start_marker(topology.workstream_id)
    end = end_marker(topology.workstream_id)
    replacement = render_marked_block(topology)

    has_start = start in content
    has_end = end in content
    if has_start != has_end:
        raise TopologyManifestError(
            f"hub marker mismatch for '{topology.workstream_id}' in '{topology.hub}'"
        )

    if has_start and has_end:
        pattern = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
        updated = pattern.sub(replacement, content, count=1)
        return updated, updated != content

    appended = content.rstrip() + "\n\n" + replacement + "\n"
    return appended, appended != content


def load_topology(manifest_path: Path) -> WorkstreamTopology:
    """Load and validate one topology manifest.

    Args:
        manifest_path: Absolute path to a TOML manifest.

    Returns:
        Parsed and validated ``WorkstreamTopology`` instance.

    Raises:
        TopologyManifestError: If required fields are missing or malformed.
    """
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

    workstream = _require_table(data, "workstream", manifest_path)
    canonical = _require_table(data, "canonical", manifest_path)
    links = _require_table(data, "links", manifest_path)

    topology = WorkstreamTopology(
        manifest_path=manifest_path,
        workstream_id=_require_str(workstream, "id", manifest_path),
        title=_require_str(workstream, "title", manifest_path),
        hub=_require_str(workstream, "hub", manifest_path),
        runbook=_require_str(canonical, "runbook", manifest_path),
        epic=_require_str(canonical, "epic", manifest_path),
        decision=_require_str(canonical, "decision", manifest_path),
        gate_task=_require_str(canonical, "gate_task", manifest_path),
        research=_require_str(canonical, "research", manifest_path),
        active_tasks=_require_list_of_str(links, "active_tasks", manifest_path),
        review_records=_require_list_of_str(links, "review_records", manifest_path),
        evidence_roots=_require_list_of_str(links, "evidence_roots", manifest_path),
    )
    _validate_manifest_paths(topology)
    return topology


def load_topologies(manifest_dir: Path = DEFAULT_MANIFEST_DIR) -> list[WorkstreamTopology]:
    """Load all workstream manifests from a directory.

    Args:
        manifest_dir: Directory containing ``*.toml`` manifests.

    Returns:
        Parsed topology manifests sorted by filename.

    Raises:
        TopologyManifestError: If directory is missing/empty or a manifest is invalid.
    """
    if not manifest_dir.exists():
        raise TopologyManifestError(f"manifest directory not found: {manifest_dir.as_posix()}")

    manifest_paths = sorted(manifest_dir.glob("*.toml"))
    if not manifest_paths:
        raise TopologyManifestError(f"no manifest files found under: {manifest_dir.as_posix()}")

    return [load_topology(path) for path in manifest_paths]


def _validate_manifest_paths(topology: WorkstreamTopology) -> None:
    """Validate repo-relative path safety for manifest paths.

    Args:
        topology: Parsed topology manifest.

    Raises:
        TopologyManifestError: If any configured path is unsafe.
    """
    markdown_paths = topology.all_markdown_paths
    invalid_markdown = [path for path in markdown_paths if not is_repo_relative(path)]
    if invalid_markdown:
        raise TopologyManifestError(
            "invalid markdown paths in manifest "
            f"'{topology.manifest_relpath}': {', '.join(invalid_markdown)}"
        )

    invalid_evidence = [path for path in topology.evidence_roots if not is_repo_relative(path)]
    if invalid_evidence:
        raise TopologyManifestError(
            "invalid evidence roots in manifest "
            f"'{topology.manifest_relpath}': {', '.join(invalid_evidence)}"
        )


def _require_table(data: dict, key: str, manifest_path: Path) -> dict:
    """Fetch and type-check a required TOML table."""
    value = data.get(key)
    if not isinstance(value, dict):
        raise TopologyManifestError(f"manifest '{manifest_path.as_posix()}' missing table [{key}]")
    return value


def _require_str(data: dict, key: str, manifest_path: Path) -> str:
    """Fetch and type-check a required string field."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TopologyManifestError(f"manifest '{manifest_path.as_posix()}' missing string '{key}'")
    return value.strip()


def _require_list_of_str(data: dict, key: str, manifest_path: Path) -> tuple[str, ...]:
    """Fetch and type-check a required list of strings field."""
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise TopologyManifestError(
            f"manifest '{manifest_path.as_posix()}' missing non-empty list '{key}'"
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TopologyManifestError(
                f"manifest '{manifest_path.as_posix()}' has non-string in '{key}'"
            )
        normalized.append(item.strip())
    return tuple(normalized)
