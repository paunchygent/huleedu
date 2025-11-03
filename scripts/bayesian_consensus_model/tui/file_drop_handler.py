"""File drop and paste handling for TUI file inputs."""

from __future__ import annotations

from pathlib import Path

FILE_DROP_TARGET_IDS = {
    "students_csv_input",
    "optimizer_output_input",
    "previous_csv_input",
    "output_input",
}


def extract_paths_from_paste(paste_text: str) -> list[str]:
    """Extract and validate file paths from pasted text.

    Handles basic quote-wrapped paths from terminal paste operations.
    Supports multiple delimiters: null bytes, newlines, commas, spaces.
    """
    if not paste_text:
        return []

    paths: list[str] = []
    paste_text = paste_text.strip()

    # Check if entire text is a single quoted string
    if (paste_text.startswith("'") and paste_text.endswith("'") and paste_text.count("'") == 2) or (
        paste_text.startswith('"') and paste_text.endswith('"') and paste_text.count('"') == 2
    ):
        segments = [paste_text]
    # Otherwise split on common delimiters
    elif "\x00" in paste_text:
        segments = paste_text.split("\x00")
    elif "\n" in paste_text:
        segments = paste_text.split("\n")
    elif "," in paste_text:
        segments = paste_text.split(",")
    else:
        # Split on space (may break paths with spaces)
        segments = paste_text.split()

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Strip quotes if present
        if (segment.startswith("'") and segment.endswith("'")) or (
            segment.startswith('"') and segment.endswith('"')
        ):
            segment = segment[1:-1]

        # Strip file:// prefix if present
        if segment.startswith("file://"):
            segment = segment.removeprefix("file://")

        # Expand ~ and validate
        try:
            path = Path(segment).expanduser()
            if path.exists():
                paths.append(str(path))
        except (OSError, ValueError):
            continue

    return paths


def unquote_file_path(value: str) -> str | None:
    """Remove quotes from file path if quotes are present and path exists.

    Args:
        value: Potentially quoted file path

    Returns:
        Unquoted path if valid, None if quotes not present or path doesn't exist
    """
    if not value:
        return None

    # Check if value is wrapped in quotes
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        unquoted = value[1:-1]
        if Path(unquoted).exists():
            return unquoted

    return None
