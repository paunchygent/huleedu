"""Module for processing essays within a batch.

Handles text cleaning, spell-checking (Ticket V4), and updating essay statuses.
"""

from __future__ import annotations

import re
from functools import lru_cache
from io import StringIO
from typing import Any

from loguru import logger
from sqlalchemy.future import select

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import (BatchStatusEnum,
                                                  ProcessedEssay,
                                                  ProcessedEssayStatusEnum)
from src.cj_essay_assessment.file_processor import generate_base_metadata
from src.cj_essay_assessment.models_api import EssayForComparison

# ────────────────────────────── spell-checker helpers ──────────────────────────


@lru_cache(maxsize=2048)
def _best_suggestion(diction: enchant.Dict, token: str) -> str | None:
    """Return the first suggestion for *token*, cached across essays."""
    suggestions = diction.suggest(token)
    return suggestions[0] if suggestions else None


def _apply_case_preservation(original: str, suggestion: str) -> str:
    """Mirror *original* capitalisation onto *suggestion* (handles iPhone/McDonald)."""
    if original.islower():
        return suggestion.lower()
    if original.isupper():
        return suggestion.upper()
    if original.istitle():
        return suggestion.capitalize()
    if len(original) == len(suggestion):
        return "".join(
            s.upper() if o.isupper() else s.lower() for o, s in zip(original, suggestion)
        )
    return suggestion[0].upper() + suggestion[1:] if original[0].isupper() else suggestion


def _analyse_and_correct(
    text: str,
    diction: enchant.Dict,
    tokenizer: type[enchant.tokenize.tokenize.Tokenizer],
) -> tuple[str, int, int]:
    """Return (corrected_text, misspelled_count, corrections_made)."""
    buf = StringIO()
    prev = 0
    misspelled = corrections = 0

    for token, offset in tokenizer(text):
        buf.write(text[prev:offset])  # delimiter slice
        prev = offset + len(token)

        if diction.check(token):
            buf.write(token)
            continue

        misspelled += 1
        suggestion = _best_suggestion(diction, token)
        if suggestion:
            fixed = _apply_case_preservation(token, suggestion)
            buf.write(fixed)
            if fixed.lower() != token.lower():
                corrections += 1
        else:
            buf.write(token)

    buf.write(text[prev:])
    return buf.getvalue(), misspelled, corrections


# ───────────────────────────── basic text cleaning ────────────────────────────


def _clean_text(text: str) -> str:
    """Normalise whitespace."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ───────────────────────────── main processing func ───────────────────────────


async def process_essays_for_batch(
    db_handler: DatabaseHandler,
    settings: Settings,
    batch_id: int,
) -> list[EssayForComparison]:
    """Processes all essays within a given batch (V4-compatible)."""

    logger.info(f"Starting essay processing for batch ID: {batch_id}")
    enchant_dict: enchant.Dict | None = None
    lang_tag = settings.spell_check_language  # NEW flag (default in config.yml)

    # 1  Initialise PyEnchant
    spell_check_unavailable = False
    if lang_tag not in settings.supported_spell_check_languages:
        logger.warning(
            f"Language '{lang_tag}' not supported; spell check disabled.",
        )
        spell_check_unavailable = True
    else:
        try:
            logger.info(f"Loading PyEnchant dictionary for '{lang_tag}'")
            enchant_dict = enchant.Dict(lang_tag)
            logger.info("Dictionary loaded.")
        except enchant.errors.DictNotFoundError:
            logger.error(f"Dictionary for '{lang_tag}' not found.")
            spell_check_unavailable = True
        except Exception as e:  # noqa: BLE001
            logger.error(f"PyEnchant init failed: {e}")
            spell_check_unavailable = True

    # 2  Process essays (everything else is your original logic)
    processed_essay_ids: list[int] = []
    essays_ready_api: list[EssayForComparison] = []

    async with db_handler.session() as session:
        batch = await db_handler.get_batch_by_id(session, batch_id, include_essays=True)
        if not batch or not batch.essays:
            logger.error(f"Batch {batch_id} not found or empty.")
            return []

        batch.status = BatchStatusEnum.PROCESSING_ESSAYS
        await session.flush()

        for essay in batch.essays:
            if essay.id is None:
                logger.error("Essay without ID; skipping.")
                continue
            processed_essay_ids.append(essay.id)

            if essay.status != ProcessedEssayStatusEnum.UPLOADED:
                logger.debug(f"Skipping essay {essay.id} (status {essay.status})")
                continue

            try:
                logger.info(f"Processing essay {essay.id} ({essay.original_filename})")

                # ── ORIGINAL file-extraction block (unchanged) ───────────────────
                # ...  <all your existing file-extraction / sanitize logic here> ...

                # a) Clean Text
                if not essay.original_content:
                    logger.warning(f"Essay {essay.id} missing content.")
                    essay.status = ProcessedEssayStatusEnum.ERROR_PROCESSING
                    meta = essay.processing_metadata or {}
                    meta["processing_error"] = {
                        "error_message": "Original content empty.",
                        "step": "TEXT_CLEANING",
                    }
                    essay.processing_metadata = meta
                    await session.flush()
                    continue

                essay.processed_content = _clean_text(essay.original_content)
                essay.status = ProcessedEssayStatusEnum.TEXT_CLEANED
                await session.flush()

                # Generate base metadata (unchanged)
                base_file_meta = generate_base_metadata(essay.processed_content)
                essay.processing_metadata = (essay.processing_metadata or {}) | {
                    "file_attributes": {
                        **base_file_meta,
                        "original_filename_provided": essay.original_filename,
                    }
                }
                await session.flush()

                # b) Spell check + correction  (NEW implementation)
                if spell_check_unavailable or enchant_dict is None:
                    essay.status = ProcessedEssayStatusEnum.ERROR_SPELLCHECK
                    essay.processing_metadata = (essay.processing_metadata or {}) | {
                        "processing_error": {
                            "error_message": "Dictionary unavailable",
                            "step": "SPELLCHECK",
                        }
                    }
                    await session.flush()
                    continue

                corrected, misspelled, corrections = _analyse_and_correct(
                    essay.processed_content,
                    enchant_dict,
                    get_tokenizer(lang_tag),
                )
                essay.text_content_corrected = corrected
                essay.processing_metadata = (essay.processing_metadata or {}) | {
                    "spell_errors_count": misspelled,
                    "spell_corrections_made_count": corrections,
                }
                essay.status = ProcessedEssayStatusEnum.SPELLCHECKED
                await session.flush()

                # c) Final transition
                essay.status = ProcessedEssayStatusEnum.READY_FOR_PAIRING
                chosen_text = (
                    essay.text_content_corrected
                    if settings.use_corrected_text_for_comparison
                    and essay.text_content_corrected
                    else essay.processed_content
                )
                essays_ready_api.append(
                    EssayForComparison(
                        id=essay.id,
                        original_filename=essay.original_filename,
                        text_content=chosen_text,
                        current_bt_score=essay.current_bt_score,
                    )
                )
                await session.flush()

            except Exception as e:  # noqa: BLE001
                logger.exception(f"Essay {essay.id} processing error")
                essay.status = ProcessedEssayStatusEnum.ERROR_PROCESSING
                essay.processing_metadata = (essay.processing_metadata or {}) | {
                    "processing_error": str(e)
                }
                await session.flush()

    # 3  ALL **your original** final-status bookkeeping starts here and is
    #     copied verbatim (no edits)  ───────────────────────────────────────────

    final_batch_status: BatchStatusEnum
    try:
        async with db_handler.session() as session:
            # Re-fetch logic -- unchanged
            if not processed_essay_ids:
                logger.info(
                    f"No essays processed for batch {batch_id}. "
                    "Determining batch status from DB."
                )
                batch_for_status_check = await db_handler.get_batch_by_id(
                    session, batch_id, include_essays=True
                )
                if batch_for_status_check and not any(
                    e.status == ProcessedEssayStatusEnum.UPLOADED
                    for e in batch_for_status_check.essays
                ):
                    all_essays_in_db = await db_handler.get_essays_by_batch(
                        session, batch_id
                    )
                    if not all_essays_in_db:
                        final_batch_status = BatchStatusEnum.ERROR_ESSAY_PROCESSING
                    else:
                        all_ready = all(
                            e.status == ProcessedEssayStatusEnum.READY_FOR_PAIRING
                            for e in all_essays_in_db
                        )
                        any_errors = any(
                            e.status
                            in (
                                ProcessedEssayStatusEnum.ERROR_PROCESSING,
                                ProcessedEssayStatusEnum.ERROR_SPELLCHECK,
                                ProcessedEssayStatusEnum.ERROR_UNSUPPORTED_FILE_TYPE,
                                ProcessedEssayStatusEnum.ERROR_FILE_READ,
                            )
                            for e in all_essays_in_db
                        )
                        if any_errors:
                            final_batch_status = BatchStatusEnum.ERROR_ESSAY_PROCESSING
                        elif all_ready:
                            final_batch_status = BatchStatusEnum.ALL_ESSAYS_READY
                        else:
                            final_batch_status = BatchStatusEnum.PROCESSING_ESSAYS
                    await db_handler.update_batch_status(
                        session, batch_id, final_batch_status
                    )
                return []  # nothing new ready

            # Re-fetch the processed essays of this run
            stmt = select(ProcessedEssay).where(
                ProcessedEssay.id.in_(processed_essay_ids)
            )
            result = await session.execute(stmt)
            final_essays_this_run = result.scalars().all()

            if not final_essays_this_run:
                logger.warning(
                    f"Could not re-fetch essays for batch {batch_id}; "
                    "setting batch error."
                )
                final_batch_status = BatchStatusEnum.ERROR_ESSAY_PROCESSING
            else:
                all_essays_in_batch_ready = True
                any_processing_errors = False
                all_batch_essays_for_final_check = await db_handler.get_essays_by_batch(
                    session, batch_id
                )
                for essay_item in all_batch_essays_for_final_check:
                    if essay_item.status != ProcessedEssayStatusEnum.READY_FOR_PAIRING:
                        all_essays_in_batch_ready = False
                    if essay_item.status in (
                        ProcessedEssayStatusEnum.ERROR_PROCESSING,
                        ProcessedEssayStatusEnum.ERROR_SPELLCHECK,
                        ProcessedEssayStatusEnum.ERROR_UNSUPPORTED_FILE_TYPE,
                        ProcessedEssayStatusEnum.ERROR_FILE_READ,
                    ):
                        any_processing_errors = True

                for essay_item_from_run in final_essays_this_run:
                    if (
                        essay_item_from_run.status
                        == ProcessedEssayStatusEnum.READY_FOR_PAIRING
                    ):
                        if (
                            essay_item_from_run.id is not None
                            and essay_item_from_run.processed_content is not None
                        ):
                            essays_ready_api.append(
                                EssayForComparison(
                                    id=essay_item_from_run.id,
                                    original_filename=essay_item_from_run.original_filename,
                                    text_content=essay_item_from_run.processed_content,
                                    current_bt_score=essay_item_from_run.current_bt_score,
                                )
                            )

                if any_processing_errors:
                    final_batch_status = BatchStatusEnum.ERROR_ESSAY_PROCESSING
                elif all_essays_in_batch_ready:
                    final_batch_status = BatchStatusEnum.ALL_ESSAYS_READY
                else:
                    final_batch_status = BatchStatusEnum.PROCESSING_ESSAYS

            await db_handler.update_batch_status(session, batch_id, final_batch_status)

    except Exception as final_status_ex:  # noqa: BLE001
        logger.exception(
            f"Error updating final status for batch {batch_id}: {final_status_ex}"
        )
        try:
            async with db_handler.session() as error_session:
                await db_handler.update_batch_status(
                    error_session,
                    batch_id,
                    BatchStatusEnum.ERROR_ESSAY_PROCESSING,
                )
        except Exception as e_update_fail:  # noqa: BLE001
            logger.critical(
                f"CRITICAL: Failed fallback status update for batch {batch_id}: "
                f"{e_update_fail}"
            )

    logger.info(
        f"Essay processing complete for batch {batch_id}. "
        f"{len(essays_ready_api)} essays ready for comparison."
    )
    return essays_ready_api
