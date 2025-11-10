"""HTTP helpers for interacting with the CJ Assessment Service."""

from __future__ import annotations

import asyncio
import uuid
from typing import Sequence

import aiohttp

from scripts.cj_experiments_runners.eng5_np.anchor_utils import extract_grade_from_filename
from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.text_extraction import extract_text, TextExtractionError


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
            grade = extract_grade_from_filename(record.path.name)
            try:
                essay_text = await asyncio.to_thread(extract_text, record.path)
            except TextExtractionError as exc:
                raise AnchorRegistrationError(str(exc)) from exc

            payload = {
                "assignment_id": str(assignment_id),
                "grade": grade,
                "essay_text": essay_text,
            }

            async with semaphore:
                async with session.post(
                    f"{cj_service_url.rstrip('/')}/api/v1/anchors/register",
                    json=payload,
                ) as response:
                    if response.status != 201:
                        body = await response.text()
                        raise AnchorRegistrationError(
                            f"Anchor registration failed ({response.status}) for {record.path.name}: {body[:200]}"
                        )
                    responses.append(await response.json())

        await asyncio.gather(*(_register(record) for record in valid_records))

    return responses
