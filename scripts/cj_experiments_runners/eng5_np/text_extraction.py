"""Utilities for extracting plain text from ENG5 runner artefacts."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


class TextExtractionError(RuntimeError):
    """Raised when raw essay content cannot be converted to plain text."""


DOCX_XML_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text(path: Path) -> str:
    """Return UTF-8 text for the given essay file.

    Supports text, markdown, and DOCX files. Raises ``TextExtractionError`` for other
    formats or malformed payloads so the caller can decide whether to
    fallback to a different workflow.
    """

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - depends on file contents
            raise TextExtractionError(f"Failed to decode text file: {path}") from exc

    if suffix == ".docx":
        return _extract_docx_text(path)

    raise TextExtractionError(f"Unsupported file type for text extraction: {path.suffix}")


def _extract_docx_text(path: Path) -> str:
    if not path.exists():
        raise TextExtractionError(f"DOCX file not found: {path}")

    try:
        with ZipFile(path) as archive:
            with archive.open("word/document.xml") as doc_xml:
                xml_data = doc_xml.read()
    except KeyError as exc:
        raise TextExtractionError("Malformed DOCX (missing document.xml)") from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise TextExtractionError(f"Failed to read DOCX: {path}") from exc

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise TextExtractionError("Invalid DOCX XML payload") from exc

    texts: list[str] = []
    for node in root.iter(f"{DOCX_XML_NAMESPACE}t"):
        if node.text:
            texts.append(node.text)

    return "\n".join(texts)
