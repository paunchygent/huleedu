#!/usr/bin/env python3
"""
Scaffold a new .claude/rules/ file with YAML frontmatter.

Usage examples:
  pdm run new-rule --title "Error Handling Patterns" \
    --type standards --scope backend

  pdm run new-rule --title "CJ Assessment Service" \
    --type service --scope backend --service-name cj_assessment_service
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from scripts.schemas.rule_schema import (
    RuleFrontmatter,
    RuleScope,
    RuleType,
    get_allowed_values,
)
from scripts.utils.frontmatter_utils import write_front_matter

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".claude" / "rules"


def slugify(text: str) -> str:
    """Convert title to kebab-case filename slug."""
    text = text.strip()
    text = re.sub(r"[\s/]+", "-", text)
    text = re.sub(r"[^A-Za-z0-9_-]+", "", text)
    return text.lower().strip("-")


def get_next_rule_id(rules_dir: Path) -> str:
    """Scan .claude/rules/ for NNN-*.md and return next available 3-digit ID.

    Finds the first available gap >= 100 to avoid collision with 0XX core rules.
    """
    existing = set()
    for p in rules_dir.glob("???-*.md"):
        stem = p.stem
        # Match NNN at start (not NNN.N sub-rules)
        if stem[:3].isdigit() and (len(stem) < 4 or stem[3] == "-"):
            existing.add(int(stem[:3]))

    # Find first available ID >= 100
    for candidate in range(100, 1000):
        if candidate not in existing:
            return f"{candidate:03d}"

    # All IDs exhausted (unlikely)
    msg = "All rule IDs 100-999 are exhausted"
    raise RuntimeError(msg)


def create_rule(args: argparse.Namespace, today: str) -> tuple[Path, dict, str]:
    """Create rule frontmatter and body with auto-increment ID."""
    rule_num = get_next_rule_id(RULES_DIR)
    slug = slugify(args.title)
    rule_id = f"{rule_num}-{slug}"

    dest = RULES_DIR / f"{rule_id}.md"

    fm: dict = {
        "id": rule_id,
        "type": args.type,
        "created": today,
        "last_updated": today,
        "scope": args.scope,
    }

    # Add optional fields
    if args.service_name:
        fm["service_name"] = args.service_name

    body = f"""# {args.title}

## Purpose

## Requirements

## Examples
"""
    return dest, fm, body


def validate_frontmatter(fm: dict) -> bool:
    """Validate frontmatter against RuleFrontmatter schema."""
    try:
        RuleFrontmatter.model_validate(fm)
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
    p = argparse.ArgumentParser(description="Create a new rule file")
    p.add_argument("--title", required=True, help="Human title for the rule")
    p.add_argument(
        "--type",
        required=True,
        choices=list(get_args(RuleType)),
        help="Rule type",
    )
    p.add_argument(
        "--scope",
        required=True,
        choices=list(get_args(RuleScope)),
        help="Rule scope",
    )
    p.add_argument(
        "--service-name",
        dest="service_name",
        help="Service name (required for service-type rules)",
    )

    args = p.parse_args(argv)
    today = dt.date.today().isoformat()

    # Validate service-name required for service type
    if args.type == "service" and not args.service_name:
        print("Error: --service-name is required for service-type rules", file=sys.stderr)
        return 1

    dest, fm, body = create_rule(args, today)

    # Check if file exists
    if dest.exists():
        print(f"Error: {dest} already exists", file=sys.stderr)
        return 2

    # Validate frontmatter
    if not validate_frontmatter(fm):
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
