"""
Topic naming implementation for Essay Lifecycle Service.

Provides production topic naming using common_core.event_enums.topic_name
following Clean Architecture dependency injection principles.
"""

from __future__ import annotations

from common_core.event_enums import ProcessingEvent, topic_name

from services.essay_lifecycle_service.protocols import TopicNamingProtocol


class DefaultTopicNaming(TopicNamingProtocol):
    """
    Production topic naming using common_core.event_enums.topic_name.

    This implementation delegates to the centralized topic_name function
    while providing a clean interface for dependency injection.
    """

    def get_topic_name(self, event: ProcessingEvent) -> str:
        """Get topic name for given processing event using centralized function."""
        return topic_name(event)
