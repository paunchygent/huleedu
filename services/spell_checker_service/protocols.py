from __future__ import annotations

from typing import Optional, Protocol
from uuid import UUID

from aiohttp import ClientSession  # Changed from placeholder

# Import concrete types instead of placeholders if they are stable
from aiokafka import AIOKafkaProducer  # Changed from placeholder

# Assuming common_core models might be used in signatures
from common_core.enums import ContentType
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import SystemProcessingMetadata


class ContentClientProtocol(Protocol):
    async def fetch_content(
        self,
        storage_id: str,
        http_session: ClientSession,  # http_session is now aiohttp.ClientSession
    ) -> str:
        """Fetches content string based on a storage ID."""
        ...


class SpellLogicProtocol(Protocol):
    async def perform_spell_check(
        self,
        text: str,
        essay_id: Optional[str],
        original_text_storage_id: str,
        initial_system_metadata: SystemProcessingMetadata,
        language: str = "en"
    ) -> SpellcheckResultDataV1:
        """Performs spell check and returns a SpellcheckResultDataV1."""
        ...


class ResultStoreProtocol(Protocol):
    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: ClientSession,
    ) -> str:
        """Stores content and returns a storage ID."""
        ...


class SpellcheckEventPublisherProtocol(Protocol):
    async def publish_spellcheck_result(
        self,
        producer: AIOKafkaProducer,
        event_data: SpellcheckResultDataV1,
        correlation_id: Optional[UUID],
    ) -> None:
        """Publishes a spell check result event to Kafka."""
        ...
