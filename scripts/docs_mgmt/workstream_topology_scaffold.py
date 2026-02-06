"""Scaffold codified workstream topology manifests and hub markers.

Purpose:
    Create one topology manifest under
    ``scripts/docs_mgmt/workstream_topology/`` and update the target hub doc
    with the generated marker block used by hub rendering.

Relationships:
    - ``scripts.docs_mgmt.workstream_topology_manifest`` for schema/marker logic
    - ``scripts.docs_mgmt.render_workstream_hubs`` for full regeneration checks
    - ``scripts.docs_mgmt.validate_workstream_topology`` for policy enforcement
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from scripts.docs_mgmt.workstream_topology_manifest import (
    DEFAULT_MANIFEST_DIR,
    ROOT,
    TopologyManifestError,
    WorkstreamTopology,
    apply_marked_block,
    is_repo_relative,
    load_topology,
)

WORKSTREAM_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ScaffoldResult:
    """Result metadata from scaffolding one workstream topology.

    Attributes:
        manifest_path: Absolute path to the created manifest.
        hub_path: Absolute path to the hub document.
        hub_updated: Whether the hub file content changed.
    """

    manifest_path: Path
    hub_path: Path
    hub_updated: bool


def build_manifest_text(topology: WorkstreamTopology) -> str:
    """Build deterministic TOML text for one topology manifest.

    Args:
        topology: Topology values to serialize.

    Returns:
        Manifest TOML text.
    """
    return "\n".join(
        [
            "[workstream]",
            f'id = "{topology.workstream_id}"',
            f'title = "{topology.title}"',
            f'hub = "{topology.hub}"',
            "",
            "[canonical]",
            f'runbook = "{topology.runbook}"',
            f'epic = "{topology.epic}"',
            f'decision = "{topology.decision}"',
            f'gate_task = "{topology.gate_task}"',
            f'research = "{topology.research}"',
            "",
            "[links]",
            _format_toml_list("active_tasks", topology.active_tasks),
            _format_toml_list("review_records", topology.review_records),
            _format_toml_list("evidence_roots", topology.evidence_roots),
            "",
        ]
    )


def scaffold_workstream_topology(
    *,
    root_dir: Path,
    manifest_dir: Path,
    workstream_id: str,
    title: str,
    hub: str,
    runbook: str,
    epic: str,
    decision: str,
    gate_task: str,
    research: str,
    active_tasks: Sequence[str],
    review_records: Sequence[str],
    evidence_roots: Sequence[str],
    force: bool,
) -> ScaffoldResult:
    """Create a topology manifest and update the target hub marker block.

    Args:
        root_dir: Repository root used for resolving relative paths.
        manifest_dir: Directory where manifests live.
        workstream_id: Stable workstream id in kebab-case.
        title: Human-readable workstream title.
        hub: Hub document path (repo-relative).
        runbook: Canonical runbook/reference path (repo-relative).
        epic: Canonical epic path (repo-relative).
        decision: Canonical decision path (repo-relative).
        gate_task: Canonical task path (repo-relative).
        research: Canonical research path (repo-relative).
        active_tasks: One or more active task paths.
        review_records: One or more review record paths.
        evidence_roots: One or more evidence root directories.
        force: Overwrite an existing manifest when ``True``.

    Returns:
        ``ScaffoldResult`` with paths and hub update status.

    Raises:
        TopologyManifestError: If inputs violate topology invariants.
    """
    _validate_workstream_id(workstream_id)
    _validate_non_empty("title", title)

    active_tuple = _normalize_and_validate_list("active-task", active_tasks)
    review_tuple = _normalize_and_validate_list("review-record", review_records)
    evidence_tuple = _normalize_and_validate_list("evidence-root", evidence_roots)

    markdown_paths = (
        hub,
        runbook,
        epic,
        decision,
        gate_task,
        research,
        *active_tuple,
        *review_tuple,
    )
    _validate_repo_relative_paths("markdown", markdown_paths)
    _validate_repo_relative_paths("evidence-root", evidence_tuple)

    manifest_path = manifest_dir / f"{workstream_id}.toml"
    if manifest_path.exists() and not force:
        raise TopologyManifestError(
            f"manifest already exists: {manifest_path.relative_to(root_dir).as_posix()}"
        )

    _ensure_markdown_paths_exist(root_dir, markdown_paths)
    _ensure_evidence_roots_exist(root_dir, evidence_tuple)

    topology = WorkstreamTopology(
        manifest_path=manifest_path,
        workstream_id=workstream_id,
        title=title.strip(),
        hub=hub.strip(),
        runbook=runbook.strip(),
        epic=epic.strip(),
        decision=decision.strip(),
        gate_task=gate_task.strip(),
        research=research.strip(),
        active_tasks=active_tuple,
        review_records=review_tuple,
        evidence_roots=evidence_tuple,
    )

    hub_path = root_dir / Path(topology.hub)
    hub_content = hub_path.read_text(encoding="utf-8")
    rendered_hub, hub_changed = apply_marked_block(hub_content, topology)

    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(build_manifest_text(topology), encoding="utf-8")
    try:
        _ = load_topology(manifest_path)
    except TopologyManifestError:
        manifest_path.unlink(missing_ok=True)
        raise

    if hub_changed:
        hub_path.write_text(rendered_hub, encoding="utf-8")

    return ScaffoldResult(manifest_path=manifest_path, hub_path=hub_path, hub_updated=hub_changed)


def _format_toml_list(key: str, values: Sequence[str]) -> str:
    """Format one TOML list field with deterministic indentation.

    Args:
        key: TOML key name.
        values: Values to serialize.

    Returns:
        TOML list snippet.
    """
    lines = [f"{key} = ["]
    for value in values:
        lines.append(f'  "{value}",')
    lines.append("]")
    return "\n".join(lines)


def _validate_workstream_id(workstream_id: str) -> None:
    """Validate workstream id format."""
    if not WORKSTREAM_ID_PATTERN.match(workstream_id):
        raise TopologyManifestError(
            "workstream id must be kebab-case (lowercase letters, digits, hyphens)"
        )


def _validate_non_empty(field_name: str, value: str) -> None:
    """Validate that a string field is non-empty."""
    if not value.strip():
        raise TopologyManifestError(f"field '{field_name}' must be non-empty")


def _normalize_and_validate_list(flag_name: str, values: Sequence[str]) -> tuple[str, ...]:
    """Normalize a repeatable CLI list and reject duplicates.

    Args:
        flag_name: CLI flag label for error messages.
        values: Raw values from arguments.

    Returns:
        Normalized tuple preserving input order.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if value in seen:
            raise TopologyManifestError(f"duplicate --{flag_name}: {value}")
        normalized.append(value)
        seen.add(value)
    if not normalized:
        raise TopologyManifestError(f"at least one --{flag_name} is required")
    return tuple(normalized)


def _validate_repo_relative_paths(label: str, paths: Sequence[str]) -> None:
    """Validate that every path is safe repo-relative."""
    invalid = [path for path in paths if not is_repo_relative(path)]
    if invalid:
        raise TopologyManifestError(
            f"invalid {label} path(s), must be repo-relative with no '..': {', '.join(invalid)}"
        )


def _ensure_markdown_paths_exist(root_dir: Path, paths: Sequence[str]) -> None:
    """Ensure each repo-relative Markdown path exists as a file."""
    missing: list[str] = []
    for path_str in paths:
        path = root_dir / Path(path_str)
        if not path.exists() or not path.is_file():
            missing.append(path_str)
    if missing:
        raise TopologyManifestError(f"missing required file path(s): {', '.join(missing)}")


def _ensure_evidence_roots_exist(root_dir: Path, roots: Sequence[str]) -> None:
    """Ensure each evidence root exists as a directory."""
    missing: list[str] = []
    for root_str in roots:
        path = root_dir / Path(root_str)
        if not path.exists() or not path.is_dir():
            missing.append(root_str)
    if missing:
        raise TopologyManifestError(
            f"missing required evidence root directorie(s): {', '.join(missing)}"
        )


def main(argv: list[str]) -> int:
    """Scaffold one workstream topology manifest from CLI args.

    Args:
        argv: Command-line arguments, excluding executable name.

    Returns:
        Process exit code (0 success, 1 failure).
    """
    parser = argparse.ArgumentParser(description="Scaffold one workstream topology manifest.")
    parser.add_argument("--id", required=True, help="Workstream id in kebab-case")
    parser.add_argument("--title", required=True, help="Human-readable workstream title")
    parser.add_argument("--hub", required=True, help="Hub markdown path (repo-relative)")
    parser.add_argument("--runbook", required=True, help="Canonical runbook/reference path")
    parser.add_argument("--epic", required=True, help="Canonical epic path")
    parser.add_argument("--decision", required=True, help="Canonical decision path")
    parser.add_argument("--gate-task", required=True, help="Canonical gate task path")
    parser.add_argument("--research", required=True, help="Canonical research path")
    parser.add_argument(
        "--active-task",
        action="append",
        default=[],
        help="Active task path (repeatable, at least one)",
    )
    parser.add_argument(
        "--review-record",
        action="append",
        default=[],
        help="Review record path (repeatable, at least one)",
    )
    parser.add_argument(
        "--evidence-root",
        action="append",
        default=[],
        help="Evidence root directory (repeatable, at least one)",
    )
    parser.add_argument(
        "--manifest-dir",
        default=str(DEFAULT_MANIFEST_DIR),
        help="Directory for topology manifests",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing manifest file")
    args = parser.parse_args(argv)

    try:
        result = scaffold_workstream_topology(
            root_dir=ROOT,
            manifest_dir=Path(args.manifest_dir),
            workstream_id=args.id,
            title=args.title,
            hub=args.hub,
            runbook=args.runbook,
            epic=args.epic,
            decision=args.decision,
            gate_task=args.gate_task,
            research=args.research,
            active_tasks=args.active_task,
            review_records=args.review_record,
            evidence_roots=args.evidence_root,
            force=args.force,
        )
    except TopologyManifestError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"Created manifest: {result.manifest_path.relative_to(ROOT).as_posix()}")
    if result.hub_updated:
        print(f"Updated hub markers: {result.hub_path.relative_to(ROOT).as_posix()}")
    else:
        print(f"Hub markers already up to date: {result.hub_path.relative_to(ROOT).as_posix()}")
    print(
        "Next step: run `pdm run validate-docs` to enforce backlink and generated-block invariants."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
