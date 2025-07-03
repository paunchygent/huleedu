"""
Development response recorder for API validation.

Simple file-based recorder for LLM responses to help validate
API contracts and debug issues during development.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings

logger = create_service_logger("llm_provider_service.response_recorder")


class DevelopmentResponseRecorder:
    """Records LLM responses to files for development only."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = (
            settings.ENVIRONMENT == "development"
            and settings.RECORD_LLM_RESPONSES
        )

        # Setup output directory
        self.output_dir = Path("./llm_response_logs")
        if self.enabled:
            self.output_dir.mkdir(exist_ok=True)
            logger.info(f"Response recorder enabled, writing to {self.output_dir}")
        else:
            logger.debug("Response recorder disabled")

    async def record_response(
        self,
        provider: str,
        request: Any,
        response: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record response to timestamped JSON file.

        Args:
            provider: LLM provider name
            request: The request object
            response: The response object
            metadata: Additional metadata to record
        """
        if not self.enabled:
            return

        try:
            timestamp = datetime.now(timezone.utc)
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
            filename = f"{provider}_{timestamp_str}.json"

            # Prepare record
            record = {
                "timestamp": timestamp.isoformat(),
                "provider": provider,
                "request": self._serialize_object(request),
                "response": self._serialize_object(response),
                "metadata": metadata or {},
                "api_version": self._get_api_version(provider),
                "service_version": "0.2.0",  # From pyproject.toml
            }

            # Write to file
            filepath = self.output_dir / filename
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(record, indent=2, default=str))

            logger.debug(f"Recorded response to {filepath}")

        except Exception as e:
            # Don't fail the request if recording fails
            logger.error(f"Failed to record response: {e}")

    async def record_error(
        self,
        provider: str,
        request: Any,
        error: Exception,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record error for debugging.

        Args:
            provider: LLM provider name
            request: The request object
            error: The exception that occurred
            metadata: Additional metadata to record
        """
        if not self.enabled:
            return

        try:
            timestamp = datetime.now(timezone.utc)
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"{provider}_error_{timestamp_str}.json"

            # Prepare error record
            record = {
                "timestamp": timestamp.isoformat(),
                "provider": provider,
                "request": self._serialize_object(request),
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": None,  # Could add traceback if needed
                },
                "metadata": metadata or {},
                "api_version": self._get_api_version(provider),
                "service_version": "0.2.0",
            }

            # Write to file
            filepath = self.output_dir / filename
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(record, indent=2, default=str))

            logger.debug(f"Recorded error to {filepath}")

        except Exception as e:
            logger.error(f"Failed to record error: {e}")

    def _serialize_object(self, obj: Any) -> Any:
        """Serialize object for JSON storage."""
        if hasattr(obj, 'model_dump'):
            # Pydantic model
            return obj.model_dump()
        elif hasattr(obj, 'dict'):
            # Older Pydantic or dict-like
            return obj.dict()
        elif isinstance(obj, dict):
            return obj
        elif isinstance(obj, (list, tuple)):
            return list(obj)
        else:
            # Convert to string for unknown types
            return str(obj)

    def _get_api_version(self, provider: str) -> str:
        """Get API version for the provider."""
        # This could be extended to track actual API versions
        api_versions = {
            "anthropic": "2024-02-15",  # Messages API version
            "openai": "v1",
            "google": "v1beta",
            "openrouter": "v1",
            "mock": "test",
        }
        return api_versions.get(provider.lower(), "unknown")

    async def cleanup_old_logs(self, days_to_keep: int = 7) -> int:
        """Clean up old log files.

        Args:
            days_to_keep: Number of days of logs to keep

        Returns:
            Number of files deleted
        """
        if not self.enabled:
            return 0

        try:
            cutoff_time = datetime.now(timezone.utc).timestamp() - (days_to_keep * 86400)
            deleted_count = 0

            for filepath in self.output_dir.glob("*.json"):
                if filepath.stat().st_mtime < cutoff_time:
                    filepath.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old response logs")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0

    def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics about recorded logs."""
        if not self.enabled:
            return {"enabled": False}

        try:
            log_files = list(self.output_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in log_files)

            # Count by provider
            provider_counts = {}
            error_count = 0
            for f in log_files:
                if "_error_" in f.name:
                    error_count += 1
                else:
                    provider = f.name.split("_")[0]
                    provider_counts[provider] = provider_counts.get(provider, 0) + 1

            return {
                "enabled": True,
                "total_files": len(log_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "error_count": error_count,
                "provider_counts": provider_counts,
                "output_directory": str(self.output_dir),
            }

        except Exception as e:
            logger.error(f"Failed to get log stats: {e}")
            return {"enabled": True, "error": str(e)}