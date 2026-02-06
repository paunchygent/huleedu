"""Validate codified workstream topology contracts.

This validator complements ``validate_docs_structure.py`` by enforcing a stable
navigation topology:
- manifests are valid and safe,
- canonical files exist,
- required docs/tasks contain backlinks to the hub, and
- generated hub topology blocks are up to date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.docs_mgmt.workstream_topology_manifest import (
    DEFAULT_MANIFEST_DIR,
    TopologyManifestError,
    apply_marked_block,
    load_topologies,
    resolve_repo_path,
)


def validate_topologies(
    manifest_dir: Path,
    *,
    check_hubs: bool,
    verbose: bool,
) -> tuple[list[str], list[str]]:
    """Validate all topology manifests under a directory.

    Args:
        manifest_dir: Directory containing ``*.toml`` topology manifests.
        check_hubs: When ``True``, fail if generated hub blocks are stale.
        verbose: When ``True``, emit additional success details.

    Returns:
        Tuple of ``(errors, warnings)``.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        topologies = load_topologies(manifest_dir)
    except TopologyManifestError as exc:
        return [str(exc)], warnings

    for topology in topologies:
        missing_files: list[str] = []
        for rel_path in topology.all_markdown_paths:
            abs_path = resolve_repo_path(rel_path)
            if not abs_path.exists():
                missing_files.append(rel_path)
            elif not abs_path.is_file():
                missing_files.append(rel_path)
            elif verbose:
                print(f"[OK] exists: {rel_path}")
        if missing_files:
            errors.append(
                f"manifest '{topology.manifest_relpath}' references missing files: "
                + ", ".join(missing_files)
            )
            continue

        missing_backlinks: list[str] = []
        for rel_path in topology.backlink_required_paths:
            text = resolve_repo_path(rel_path).read_text(encoding="utf-8")
            if topology.hub not in text:
                missing_backlinks.append(rel_path)
        if missing_backlinks:
            errors.append(
                f"manifest '{topology.manifest_relpath}' missing hub backlink "
                f"('{topology.hub}') in: " + ", ".join(missing_backlinks)
            )

        if check_hubs:
            hub_path = resolve_repo_path(topology.hub)
            hub_text = hub_path.read_text(encoding="utf-8")
            try:
                rendered_hub, changed = apply_marked_block(hub_text, topology)
                _ = rendered_hub
            except TopologyManifestError as exc:
                errors.append(str(exc))
                continue
            if changed:
                errors.append(
                    "stale generated topology block in hub "
                    f"'{topology.hub}'. Run: pdm run render-workstream-hubs"
                )
            elif verbose:
                print(f"[OK] hub topology block up to date: {topology.hub}")

    return errors, warnings


def main(argv: list[str]) -> int:
    """Run topology validation from CLI.

    Args:
        argv: Command-line arguments, excluding executable name.

    Returns:
        Process exit code (0 success, 1 validation failure).
    """
    parser = argparse.ArgumentParser(description="Validate workstream topology manifests.")
    parser.add_argument(
        "--manifest-dir",
        default=str(DEFAULT_MANIFEST_DIR),
        help="Directory containing *.toml topology manifests",
    )
    parser.add_argument(
        "--check-hubs",
        action="store_true",
        help="Fail if generated topology blocks in hub docs are stale",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show successful checks")
    args = parser.parse_args(argv)

    errors, warnings = validate_topologies(
        Path(args.manifest_dir),
        check_hubs=args.check_hubs,
        verbose=args.verbose,
    )

    for warning in warnings:
        print(f"[WARNING] {warning}")
    for error in errors:
        print(f"[ERROR] {error}")

    if errors:
        print("\nValidation failed.")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
