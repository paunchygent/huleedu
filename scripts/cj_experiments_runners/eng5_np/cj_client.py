"""HTTP helpers for interacting with the CJ Assessment Service."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Sequence

import aiohttp

from scripts.cj_experiments_runners.eng5_np.anchor_utils import extract_grade_from_filename
from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.text_extraction import TextExtractionError, extract_text


class AnchorRegistrationError(RuntimeError):
    """Raised when CJ anchor registration fails."""


async def register_anchor_essays(
    *,
    anchors: Sequence[FileRecord],
    assignment_id: uuid.UUID,
    cj_service_url: str,
    max_concurrent: int = 4,
) -> list[dict]:
    """Register anchor essays via CJ API and return response payloads."""

    valid_records = [record for record in anchors if record.exists]
    if not valid_records:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=60)
    responses: list[dict] = []

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def _register(record: FileRecord) -> None:
            filename = record.path.name
            grade = extract_grade_from_filename(filename)
            anchor_label = Path(filename).stem
            try:
                essay_text = await asyncio.to_thread(extract_text, record.path)
            except TextExtractionError as exc:
                raise AnchorRegistrationError(str(exc)) from exc

            payload = {
                "assignment_id": str(assignment_id),
                "grade": grade,
                "anchor_label": anchor_label,
                "essay_text": essay_text,
            }

            async with semaphore:
                async with session.post(
                    f"{cj_service_url.rstrip('/')}/api/v1/anchors/register",
                    json=payload,
                ) as response:
                    if response.status != 201:
                        body = await response.text()
                        message = (
                            f"Anchor registration failed ({response.status}) for "
                            f"{record.path.name}: {body[:200]}"
                        )
                        raise AnchorRegistrationError(message)
                    responses.append(await response.json())

        await asyncio.gather(*(_register(record) for record in valid_records))

    return responses
