"""Shared frontmatter utilities for task/docs/rules management scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown file.

    Args:
        path: Path to markdown file

    Returns:
        Tuple of (frontmatter dict, body content). Returns ({}, full_text) if no frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    # Split on first occurrence of closing ---
    parts = text[4:].split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    header_text = parts[0]
    body = parts[1]

    try:
        data = yaml.safe_load(header_text) or {}
    except yaml.YAMLError:
        return {}, text

    return data, body


def write_front_matter(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write markdown file with YAML frontmatter.

    Args:
        path: Path to write
        frontmatter: Dict to serialize as YAML frontmatter
        body: Markdown body content
    """
    yaml_content = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    content = f"---\n{yaml_content}---\n{body}"
    path.write_text(content, encoding="utf-8")


def validate_frontmatter_against_schema(
    data: dict[str, Any],
    schema_class: type,
) -> tuple[bool, list[str]]:
    """Validate frontmatter dict against Pydantic schema.

    Args:
        data: Frontmatter dict to validate
        schema_class: Pydantic model class

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    try:
        schema_class(**data)
        return True, []
    except Exception as e:
        errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                field = ".".join(str(x) for x in err["loc"])
                errors.append(f"{field}: {err['msg']}")
        else:
            errors.append(str(e))
        return False, errors
