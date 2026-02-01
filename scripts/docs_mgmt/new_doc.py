#!/usr/bin/env python3
"""
Scaffold a new documentation file with YAML frontmatter.

Usage examples:
  pdm run new-doc --type runbook --title "Service Recovery" \
    --service cj_assessment_service --severity high

  pdm run new-doc --type adr --title "Cache Strategy"

  pdm run new-doc --type epic --title "User Dashboard" --id EPIC-010

  pdm run new-doc --type review --title "Review: Story approval" \
    --story us-00ya-workflow-continuation-refactor--phase-6 --reviewer @lead

  pdm run new-doc --type reference --title "TASKS lifecycle v2"

  pdm run new-doc --type research --title "Investigate Jira ↔ TASKS sync options"
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from scripts.schemas.docs_schema import (
    DecisionFrontmatter,
    EpicFrontmatter,
    EpicStatus,
    ReferenceFrontmatter,
    ReferenceStatus,
    ResearchFrontmatter,
    ResearchStatus,
    ReviewFrontmatter,
    ReviewStatus,
    RunbookFrontmatter,
    RunbookSeverity,
    get_allowed_values,
)
from scripts.utils.frontmatter_utils import write_front_matter

ROOT = Path(__file__).resolve().parents[2]

# Output directories by doc type
DOC_OUTPUT_PATHS = {
    "runbook": ROOT / "docs" / "operations",
    "adr": ROOT / "docs" / "decisions",
    "epic": ROOT / "docs" / "product" / "epics",
    "review": ROOT / "docs" / "product" / "reviews",
    "reference": ROOT / "docs" / "reference",
    "research": ROOT / "docs" / "research",
}


def slugify(text: str) -> str:
    """Convert title to kebab-case filename slug."""
    text = text.strip()
    text = re.sub(r"[\s/_]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9_-]+", "", text)
    return text.lower().strip("-")


def get_next_adr_id(decisions_dir: Path) -> str:
    """Scan docs/decisions/ for NNNN-*.md and return next 4-digit ID."""
    existing = [p.stem for p in decisions_dir.glob("????-*.md")]
    if not existing:
        return "0001"
    ids = [int(s[:4]) for s in existing if s[:4].isdigit()]
    if not ids:
        return "0001"
    return f"{max(ids) + 1:04d}"


def get_next_epic_id(epics_dir: Path) -> str:
    """Scan docs/product/epics/ for existing EPIC-NNN patterns and return next ID."""
    existing = list(epics_dir.glob("*.md"))
    max_id = 0
    for p in existing:
        # Read frontmatter to find id field
        text = p.read_text(encoding="utf-8")
        match = re.search(r"^id:\s*['\"]?EPIC-(\d{3})['\"]?", text, re.MULTILINE)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"EPIC-{max_id + 1:03d}"


def create_runbook(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create runbook frontmatter and body."""
    slug = slugify(args.title)
    dest = DOC_OUTPUT_PATHS["runbook"] / f"{slug}.md"

    fm = {
        "type": "runbook",
        "service": args.service,
        "severity": args.severity,
        "last_reviewed": today,
    }

    body = f"""# {args.title}

## Symptoms

## Diagnosis

## Resolution

## Prevention
"""
    return dest, fm, body


def create_adr(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create ADR frontmatter and body with auto-increment ID."""
    decisions_dir = DOC_OUTPUT_PATHS["adr"]
    adr_num = get_next_adr_id(decisions_dir)
    adr_id = f"ADR-{adr_num}"

    slug = slugify(args.title)
    dest = decisions_dir / f"{adr_num}-{slug}.md"

    fm = {
        "type": "decision",
        "id": adr_id,
        "status": "proposed",
        "created": today,
        "last_updated": today,
    }

    body = f"""# {adr_id}: {args.title}

## Status

Proposed

## Context

## Decision

## Consequences
"""
    return dest, fm, body


def create_epic(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create epic frontmatter and body."""
    epics_dir = DOC_OUTPUT_PATHS["epic"]

    # Use provided ID or auto-generate
    epic_id = args.id if args.id else get_next_epic_id(epics_dir)

    slug = slugify(args.title)
    dest = epics_dir / f"{slug}.md"

    fm = {
        "type": "epic",
        "id": epic_id,
        "title": args.title,
        "status": args.status,
        "phase": args.phase,
        "sprint_target": args.sprint_target,
        "created": today,
        "last_updated": today,
    }

    body = f"""# {epic_id}: {args.title}

## Summary

## Deliverables

## User Stories

## References
"""
    return dest, fm, body


def create_review(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create review frontmatter and body."""
    slug = slugify(args.story or args.title)
    dest = DOC_OUTPUT_PATHS["review"] / f"review-{slug}.md"

    fm = {
        "type": "review",
        "id": f"REV-{slug}",
        "title": args.title,
        "status": args.status,
        "created": today,
        "last_updated": today,
        "story": args.story,
        "reviewer": args.reviewer,
    }

    body = f"""# {args.title}

## TL;DR

## Problem Statement

## Proposed Solution

## Scope

## Risks / Unknowns

## Verdict

**Status:** `{args.status}`
"""
    return dest, fm, body


def create_reference(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create reference frontmatter and body."""
    slug = slugify(args.title)
    dest = DOC_OUTPUT_PATHS["reference"] / f"ref-{slug}.md"

    fm = {
        "type": "reference",
        "id": f"REF-{slug}",
        "title": args.title,
        "status": args.status,
        "created": today,
        "last_updated": today,
        "topic": args.topic,
    }

    body = f"""# {args.title}

## Purpose

## Canonical Rules

## Examples
"""
    return dest, fm, body


def create_research(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create research frontmatter and body."""
    slug = slugify(args.title)
    dest = DOC_OUTPUT_PATHS["research"] / f"research-{slug}.md"

    fm = {
        "type": "research",
        "id": f"RES-{slug}",
        "title": args.title,
        "status": args.status,
        "created": today,
        "last_updated": today,
    }

    body = f"""# {args.title}

## Question

## Findings

## Decision / Next Steps
"""
    return dest, fm, body


def validate_frontmatter(doc_type: str, fm: dict) -> bool:
    """Validate frontmatter against appropriate schema."""
    schema_map = {
        "runbook": RunbookFrontmatter,
        "adr": DecisionFrontmatter,
        "epic": EpicFrontmatter,
        "review": ReviewFrontmatter,
        "reference": ReferenceFrontmatter,
        "research": ResearchFrontmatter,
    }
    schema = schema_map[doc_type]

    try:
        schema.model_validate(fm)
        return True
    except ValidationError as e:
        print("Frontmatter validation failed:", file=sys.stderr)
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            print(f"  {loc}: {err['msg']}", file=sys.stderr)
        return False


def print_allowed_values() -> None:
    """Print allowed enum values for CLI reference."""
    print("\nAllowed values for reference:")
    allowed = get_allowed_values()
    for field, values in allowed.items():
        print(f"  {field}: {', '.join(values)}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Create a new documentation file")
    p.add_argument(
        "--type",
        required=True,
        choices=["runbook", "adr", "epic", "review", "reference", "research"],
        help="Document type to create",
    )
    p.add_argument("--title", required=True, help="Human title for the document")

    # Runbook-specific args
    p.add_argument("--service", help="Service name (required for runbooks)")
    p.add_argument(
        "--severity",
        choices=list(get_args(RunbookSeverity)),
        help="Severity level (required for runbooks)",
    )

    # Epic-specific args
    p.add_argument("--id", help="Epic ID (e.g., EPIC-010), auto-generated if omitted")
    p.add_argument(
        "--status",
        help="Document status (enum depends on --type)",
    )
    p.add_argument("--phase", type=int, help="Epic phase number")
    p.add_argument("--sprint-target", dest="sprint_target", help="Target sprint")

    # Review-specific args
    p.add_argument("--story", help="Optional TASKS story id being reviewed (kebab-case)")
    p.add_argument("--reviewer", help="Optional reviewer handle (e.g., @lead)")

    # Reference-specific args
    p.add_argument("--topic", help="Optional topic tag for reference docs")

    args = p.parse_args(argv)
    today = dt.date.today().isoformat()

    # Validate required args per type
    if args.type == "runbook":
        if not args.service:
            print("Error: --service is required for runbooks", file=sys.stderr)
            return 1
        if not args.severity:
            print("Error: --severity is required for runbooks", file=sys.stderr)
            return 1
        dest, fm, body = create_runbook(args, today)

    elif args.type == "adr":
        dest, fm, body = create_adr(args, today)

    elif args.type == "epic":
        if not args.status:
            args.status = "draft"
        # Validate epic ID format if provided
        if args.id and not re.match(r"^EPIC-\d{3}$", args.id):
            print(
                "Error: --id must match pattern EPIC-NNN (e.g., EPIC-010)",
                file=sys.stderr,
            )
            return 1
        if args.status not in list(get_args(EpicStatus)):
            allowed = ", ".join(list(get_args(EpicStatus)))
            print(f"Error: --status must be one of: {allowed}", file=sys.stderr)
            return 1
        dest, fm, body = create_epic(args, today)

    elif args.type == "review":
        if not args.status:
            args.status = "pending"
        if args.status not in list(get_args(ReviewStatus)):
            allowed = ", ".join(list(get_args(ReviewStatus)))
            print(f"Error: --status must be one of: {allowed}", file=sys.stderr)
            return 1
        dest, fm, body = create_review(args, today)

    elif args.type == "reference":
        if not args.status:
            args.status = "active"
        if args.status not in list(get_args(ReferenceStatus)):
            allowed = ", ".join(list(get_args(ReferenceStatus)))
            print(f"Error: --status must be one of: {allowed}", file=sys.stderr)
            return 1
        dest, fm, body = create_reference(args, today)

    elif args.type == "research":
        if not args.status:
            args.status = "active"
        if args.status not in list(get_args(ResearchStatus)):
            allowed = ", ".join(list(get_args(ResearchStatus)))
            print(f"Error: --status must be one of: {allowed}", file=sys.stderr)
            return 1
        dest, fm, body = create_research(args, today)

    else:
        print(f"Error: Unknown type {args.type}", file=sys.stderr)
        return 1

    # Check if file exists
    if dest.exists():
        print(f"Error: {dest} already exists", file=sys.stderr)
        return 2

    # Validate frontmatter
    if not validate_frontmatter(args.type, fm):
        return 1

    # Create parent directory if needed
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    write_front_matter(dest, fm, body)
    print(f"Created {dest.relative_to(ROOT)}")
    print_allowed_values()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
