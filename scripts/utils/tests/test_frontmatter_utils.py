"""Tests for frontmatter_utils module."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from scripts.utils.frontmatter_utils import (
    read_front_matter,
    validate_frontmatter_against_schema,
    write_front_matter,
)


class TestReadFrontMatter:
    """Tests for read_front_matter function."""

    def test_parses_valid_frontmatter(self, tmp_path: Path) -> None:
        """Should parse valid YAML frontmatter."""
        content = """---
id: test-task
title: Test Task
status: in_progress
priority: high
---
# Body Content

Some markdown here.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm["id"] == "test-task"
        assert fm["title"] == "Test Task"
        assert fm["status"] == "in_progress"
        assert fm["priority"] == "high"
        assert "# Body Content" in body

    def test_returns_empty_dict_when_no_frontmatter(self, tmp_path: Path) -> None:
        """Should return empty dict when file has no frontmatter."""
        content = "# Just a heading\n\nSome content."
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm == {}
        assert body == content

    def test_returns_empty_dict_when_malformed_frontmatter(self, tmp_path: Path) -> None:
        """Should return empty dict when frontmatter is malformed."""
        content = """---
id: test
title: [invalid yaml
---
Body content.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm == {}

    def test_handles_list_values(self, tmp_path: Path) -> None:
        """Should parse list values in frontmatter."""
        content = """---
id: test-task
labels:
  - dev-tooling
  - infrastructure
related:
  - EPIC-007
  - ADR-0019
---
Body content.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm["labels"] == ["dev-tooling", "infrastructure"]
        assert fm["related"] == ["EPIC-007", "ADR-0019"]

    def test_handles_empty_frontmatter(self, tmp_path: Path) -> None:
        """Should return empty dict for empty frontmatter block."""
        content = """---
---
Body content.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm == {}
        assert "Body content" in body

    def test_returns_empty_when_no_closing_delimiter(self, tmp_path: Path) -> None:
        """Should return empty dict when closing delimiter is missing."""
        content = """---
id: test
title: Test
Body without closing delimiter.
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)

        fm, body = read_front_matter(file_path)

        assert fm == {}


class TestWriteFrontMatter:
    """Tests for write_front_matter function."""

    def test_writes_frontmatter_and_body(self, tmp_path: Path) -> None:
        """Should write file with frontmatter and body."""
        file_path = tmp_path / "output.md"
        frontmatter = {"id": "test-task", "title": "Test Task", "status": "pending"}
        body = "# Test Content\n\nSome markdown."

        write_front_matter(file_path, frontmatter, body)

        content = file_path.read_text()
        assert content.startswith("---\n")
        assert "id: test-task" in content
        assert "title: Test Task" in content
        assert "---\n# Test Content" in content

    def test_roundtrip_preserves_data(self, tmp_path: Path) -> None:
        """Should preserve data through write/read roundtrip."""
        file_path = tmp_path / "roundtrip.md"
        original_fm = {
            "id": "test-task",
            "title": "Test Task",
            "labels": ["label1", "label2"],
        }
        original_body = "# Content\n\nBody text."

        write_front_matter(file_path, original_fm, original_body)
        read_fm, read_body = read_front_matter(file_path)

        assert read_fm["id"] == original_fm["id"]
        assert read_fm["title"] == original_fm["title"]
        assert read_fm["labels"] == original_fm["labels"]
        assert original_body in read_body


class TestValidateFrontmatterAgainstSchema:
    """Tests for validate_frontmatter_against_schema function."""

    def test_returns_true_for_valid_data(self) -> None:
        """Should return (True, []) for valid data."""

        class SimpleSchema(BaseModel):
            id: str
            title: str

        data = {"id": "test", "title": "Test Title"}

        is_valid, errors = validate_frontmatter_against_schema(data, SimpleSchema)

        assert is_valid is True
        assert errors == []

    def test_returns_false_with_errors_for_invalid_data(self) -> None:
        """Should return (False, errors) for invalid data."""

        class SimpleSchema(BaseModel):
            id: str
            title: str

        data = {"id": "test"}  # missing required 'title'

        is_valid, errors = validate_frontmatter_against_schema(data, SimpleSchema)

        assert is_valid is False
        assert len(errors) > 0
        assert any("title" in e for e in errors)

    def test_returns_field_specific_errors(self) -> None:
        """Should return field-specific error messages."""

        class StrictSchema(BaseModel):
            count: int

        data = {"count": "not-an-int"}

        is_valid, errors = validate_frontmatter_against_schema(data, StrictSchema)

        assert is_valid is False
        assert any("count" in e for e in errors)
