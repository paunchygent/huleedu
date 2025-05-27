from __future__ import annotations

import asyncio
from typing import Optional, Tuple

import aiohttp  # For ClientSession type hint
from aiohttp import ClientTimeout

# from common_core.enums import ContentType # Not directly used by these low-level functions
# from common_core.events.spellcheck_models import SpellcheckResultDataV1 # Not directly returned
# from common_core.metadata_models import StorageReferenceMetadata # Not directly used
from huleedu_service_libs.logging_utils import create_service_logger

# Protocols are not implemented here, but these functions can be *used* by their implementations
# from .protocols import (
#     ContentClientProtocol,
#     ResultStoreProtocol,
#     SpellLogicProtocol,
# )

logger = create_service_logger("spell_checker_service.core_logic")


# --- Default Implementations / Helpers ---

async def default_fetch_content_impl(
    session: aiohttp.ClientSession,
    storage_id: str,
    content_service_url: str,
    essay_id: Optional[str] = None
) -> str:
    """
    Default implementation for fetching content from the content service.
    Raises exception on failure.
    """
    url = f"{content_service_url}/{storage_id}"
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    logger.debug(f"{log_prefix}Fetching content from URL: {url}")
    try:
        timeout = ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            content = await response.text()
            logger.debug(
                f"{log_prefix}Fetched content from {storage_id} "
                f"(first 100 chars: {content[:100]})"
            )
            return content
    except Exception as e:
        logger.error(
            f"{log_prefix}Error fetching content {storage_id} from {url}: {e}",
            exc_info=True,
        )
        raise # Re-raise after logging


async def default_store_content_impl(
    session: aiohttp.ClientSession,
    text_content: str,
    content_service_url: str,
    essay_id: Optional[str] = None,
) -> str:
    """
    Default implementation for storing content to the content service.
    Raises exception on failure.
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    logger.debug(
        f"{log_prefix}Storing content (length: {len(text_content)}) "
        f"to Content Service via {content_service_url}"
    )
    try:
        timeout = ClientTimeout(total=10)
        async with session.post(
            content_service_url, data=text_content.encode("utf-8"), timeout=timeout
        ) as response:
            response.raise_for_status()
            # Assuming Content Service returns JSON like {"storage_id": "..."}
            data: dict[str, str] = await response.json()
            storage_id = data.get("storage_id")
            if not storage_id:
                raise ValueError("Content service response did not include 'storage_id'")
            logger.info(f"{log_prefix}Stored corrected text, new_storage_id: {storage_id}")
            return storage_id
    except Exception as e:
        logger.error(f"{log_prefix}Error storing content: {e}", exc_info=True)
        raise # Re-raise after logging


async def default_perform_spell_check_algorithm(
    text: str,
    essay_id: Optional[str] = None
) -> Tuple[str, int]:
    """
    Core spell check algorithm.
    This is a simple placeholder implementation. Returns (corrected_text, corrections_count).
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    logger.info(
        f"{log_prefix}Performing DUMMY spell check algorithm for text "
        f"(length: {len(text)})"
    )
    await asyncio.sleep(0.1)  # Simulate work

    # Simple dummy corrections - replace with actual spell check logic
    corrected_text = text.replace("teh", "the").replace("recieve", "receive")
    corrections_count = text.count("teh") + text.count("recieve")

    logger.info(f"{log_prefix}Dummy spell check algorithm made {corrections_count} corrections.")
    return corrected_text, corrections_count


# The classes ContentClient, ResultStore, SpellLogic that implement the protocols
# will likely live in event_router.py or a new di.py and use these _impl functions.
# For now, core_logic.py provides these fundamental pieces.
