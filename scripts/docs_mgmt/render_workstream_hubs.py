"""Render generated topology blocks into workstream hub documents.

This script reads topology manifests and writes/validates generated navigation
sections in hub reference docs. It uses the shared parser/renderer in
``scripts.docs_mgmt.workstream_topology_manifest``.
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


def render_hubs(
    manifest_dir: Path,
    *,
    check: bool,
    verbose: bool,
) -> tuple[list[str], list[str], int]:
    """Render or check generated hub blocks for all manifests.

    Args:
        manifest_dir: Directory containing ``*.toml`` topology manifests.
        check: When ``True``, do not write files and fail if any hub is stale.
        verbose: When ``True``, print per-hub status.

    Returns:
        Tuple of ``(errors, stale_hubs, updated_count)``.
    """
    errors: list[str] = []
    stale_hubs: list[str] = []
    updated_count = 0

    try:
        topologies = load_topologies(manifest_dir)
    except TopologyManifestError as exc:
        return [str(exc)], stale_hubs, updated_count

    for topology in topologies:
        hub_path = resolve_repo_path(topology.hub)
        if not hub_path.exists():
            errors.append(f"hub file not found: {topology.hub}")
            continue

        try:
            original = hub_path.read_text(encoding="utf-8")
            rendered, changed = apply_marked_block(original, topology)
        except TopologyManifestError as exc:
            errors.append(str(exc))
            continue

        if changed and check:
            stale_hubs.append(topology.hub)
            continue

        if changed and not check:
            hub_path.write_text(rendered, encoding="utf-8")
            updated_count += 1
            if verbose:
                print(f"[UPDATED] {topology.hub}")
        elif verbose:
            print(f"[OK] {topology.hub}")

    return errors, stale_hubs, updated_count


def main(argv: list[str]) -> int:
    """Run the hub renderer from CLI.

    Args:
        argv: Command-line arguments, excluding executable name.

    Returns:
        Process exit code (0 success, 1 failure).
    """
    parser = argparse.ArgumentParser(description="Render generated workstream hub sections.")
    parser.add_argument(
        "--manifest-dir",
        default=str(DEFAULT_MANIFEST_DIR),
        help="Directory containing *.toml topology manifests",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that hubs are up to date without writing",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-hub status")
    args = parser.parse_args(argv)

    errors, stale_hubs, updated_count = render_hubs(
        Path(args.manifest_dir),
        check=args.check,
        verbose=args.verbose,
    )

    for error in errors:
        print(f"[ERROR] {error}")
    if stale_hubs:
        print("[ERROR] stale generated hub topology blocks:")
        for hub in stale_hubs:
            print(f"  - {hub}")

    if errors or stale_hubs:
        return 1

    if args.check:
        print("All generated hub topology blocks are up to date.")
    else:
        print(f"Rendered generated hub topology blocks. Updated: {updated_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
