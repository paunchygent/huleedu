"""Utilities for loading spell normalization whitelists."""

from __future__ import annotations

from pathlib import Path

from huleedu_nlp_shared.normalization.protocols import WhitelistProtocol


class FileWhitelist(WhitelistProtocol):
    """Load a whitelist file (one token per line) into memory."""

    def __init__(self, path: str | Path) -> None:
        self._source_path = Path(path)
        self._entries: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._source_path.exists():
            raise FileNotFoundError(
                f"Whitelist file not found at {self._source_path}. Configure the path correctly."
            )

        with self._source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                token = line.strip()
                if token:
                    self._entries.add(token.lower())

    def is_whitelisted(self, word: str) -> bool:
        """Return True when the token should bypass corrections."""

        return word.lower() in self._entries

    @property
    def size(self) -> int:
        """Return the number of entries in the whitelist."""

        return len(self._entries)

    @property
    def source_path(self) -> Path:
        """Expose the source path for observability/reporting."""

        return self._source_path
