"""Asset inventory helpers for the ENG5 NP runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import typer

from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.utils import sanitize_identifier, sha256_of_file


@dataclass(frozen=True)
class FileRecord:
    """Metadata about a single file on disk."""

    path: Path
    exists: bool
    size_bytes: int | None = None
    checksum: str | None = None

    @classmethod
    def from_path(cls, path: Path, compute_checksum: bool = True) -> "FileRecord":
        if not path.exists():
            return cls(path=path, exists=False)
        if path.is_file():
            size = path.stat().st_size
            checksum = sha256_of_file(path) if compute_checksum else None
            return cls(path=path, exists=True, size_bytes=size, checksum=checksum)
        return cls(path=path, exists=True)


@dataclass(frozen=True)
class DirectorySnapshot:
    """Summary of files discovered under a directory."""

    root: Path
    files: Sequence[FileRecord]

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def missing(self) -> bool:
        return not self.root.exists()


@dataclass(frozen=True)
class RunnerInventory:
    instructions: FileRecord
    prompt: FileRecord
    anchors_csv: FileRecord
    anchors_xlsx: FileRecord
    anchor_docs: DirectorySnapshot
    student_docs: DirectorySnapshot


def snapshot_directory(path: Path, patterns: Iterable[str]) -> DirectorySnapshot:
    """Return metadata for files under *path* matching *patterns*."""

    files: list[FileRecord] = []
    if path.exists():
        for pattern in patterns:
            for entry in sorted(path.glob(pattern)):
                if entry.is_file():
                    files.append(FileRecord.from_path(entry))
    return DirectorySnapshot(root=path, files=files)


def collect_inventory(paths: RunnerPaths) -> RunnerInventory:
    """Build the current ENG5 NP asset inventory."""

    anchor_patterns = ("*.docx", "*.pdf", "*.txt")
    student_patterns = ("*.docx", "*.pdf")
    return RunnerInventory(
        instructions=FileRecord.from_path(paths.instructions_path),
        prompt=FileRecord.from_path(paths.prompt_path),
        anchors_csv=FileRecord.from_path(paths.anchors_csv),
        anchors_xlsx=FileRecord.from_path(paths.anchors_xlsx),
        anchor_docs=snapshot_directory(paths.anchor_docs_dir, anchor_patterns),
        student_docs=snapshot_directory(paths.student_docs_dir, student_patterns),
    )


def ensure_execute_requirements(inventory: RunnerInventory) -> None:
    """Raise if critical ENG5 artefacts are missing for execute mode."""

    missing: list[str] = []
    if not inventory.instructions.exists:
        missing.append(f"Missing instructions: {inventory.instructions.path}")
    if not inventory.prompt.exists:
        missing.append(f"Missing prompt reference: {inventory.prompt.path}")
    if inventory.student_docs.count == 0:
        missing.append(
            f"No student essays found in {inventory.student_docs.root}. Add files before execute."
        )
    if missing:
        joined = "\n - ".join(missing)
        raise FileNotFoundError(f"Execute mode prerequisites not met:\n - {joined}")


def print_inventory(inventory: RunnerInventory) -> None:
    """Emit a human-readable summary for plan mode."""

    typer.echo("\nENG5 NP Asset Inventory\n========================")
    _print_file("Instructions", inventory.instructions)
    _print_file("Prompt", inventory.prompt)
    _print_file("Anchors CSV", inventory.anchors_csv)
    _print_file("Anchors XLSX", inventory.anchors_xlsx)
    _print_snapshot("Anchor essays", inventory.anchor_docs)
    _print_snapshot("Student essays", inventory.student_docs)


def _print_file(label: str, record: FileRecord) -> None:
    exists_marker = "✅" if record.exists else "❌"
    size_info = f" ({record.size_bytes:,} bytes)" if record.size_bytes is not None else ""
    typer.echo(f"{exists_marker} {label}: {record.path}{size_info}")


def _print_snapshot(label: str, snapshot: DirectorySnapshot) -> None:
    if snapshot.missing:
        typer.echo(f"❌ {label}: missing -> {snapshot.root}")
        return
    typer.echo(f"✅ {label}: {snapshot.count} files under {snapshot.root}")


def build_essay_refs(
    *,
    anchors: Sequence[FileRecord],
    students: Sequence[FileRecord],
) -> list:
    """Create essay refs combining anchor and student files."""

    from common_core.metadata_models import EssayProcessingInputRefV1

    refs: list[EssayProcessingInputRefV1] = []
    refs.extend(_records_to_refs(anchors, prefix="anchor"))
    refs.extend(_records_to_refs(students, prefix="student"))
    return refs


def _records_to_refs(records: Sequence[FileRecord], prefix: str) -> list:
    from common_core.metadata_models import EssayProcessingInputRefV1

    refs: list[EssayProcessingInputRefV1] = []
    for record in records:
        if not record.exists:
            continue
        essay_id = sanitize_identifier(record.path.stem)
        checksum = record.checksum or sha256_of_file(record.path)
        text_storage_id = f"{prefix}::{checksum}"
        refs.append(
            EssayProcessingInputRefV1(
                essay_id=essay_id,
                text_storage_id=text_storage_id,
            )
        )
    return refs
