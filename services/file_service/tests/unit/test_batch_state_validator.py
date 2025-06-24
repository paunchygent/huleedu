"""Unit tests for BOSBatchStateValidator with proper enum usage."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from common_core.pipeline_models import PipelineExecutionStatus
from services.file_service.implementations.batch_state_validator import BOSBatchStateValidator


class TestBOSBatchStateValidator:

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.BOS_URL = "http://test-bos:5000"
        return settings

    @pytest.fixture
    def validator(self, mock_session, mock_settings):
        return BOSBatchStateValidator(mock_session, mock_settings)

    def _setup_mock_response(self, mock_session, status_code, json_data):
        """Helper to properly setup async context manager mock."""
        mock_response = AsyncMock()
        mock_response.status = status_code
        mock_response.json.return_value = json_data

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get

    async def test_can_modify_unlocked_batch(self, validator, mock_session):
        """Test validation allows modification of unlocked batch using proper enums."""
        # Setup mock response with no active processing
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.PENDING_DEPENDENCIES.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is True
        assert reason == "Batch can be modified"

    async def test_cannot_modify_batch_in_progress(self, validator, mock_session):
        """Test validation blocks modification when batch has IN_PROGRESS status."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.IN_PROGRESS.value,
                    "essay_counts": {
                        "total": 5,
                        "pending_dispatch_or_processing": 3,
                        "successful": 2,
                        "failed": 0
                    },
                    "started_at": "2023-01-01T10:00:00Z",
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": 40.0
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert "spellcheck processing has started" in reason

    async def test_cannot_modify_batch_dispatch_initiated(self, validator, mock_session):
        """Test validation blocks modification when batch has DISPATCH_INITIATED status."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.DISPATCH_INITIATED.value,
                    "essay_counts": {
                        "total": 5,
                        "pending_dispatch_or_processing": 5,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": "2023-01-01T10:00:00Z",
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": 0.0
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert "spellcheck processing has started" in reason

    async def test_cannot_modify_completed_batch(self, validator, mock_session):
        """Test validation blocks modification when batch is completed."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value,
                    "essay_counts": {
                        "total": 5,
                        "pending_dispatch_or_processing": 0,
                        "successful": 5,
                        "failed": 0
                    },
                    "started_at": "2023-01-01T10:00:00Z",
                    "completed_at": "2023-01-01T10:30:00Z",
                    "error_info": None,
                    "progress_percentage": 100.0
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert "spellcheck processing has started" in reason

    async def test_cannot_modify_batch_partial_success(self, validator, mock_session):
        """Test validation blocks modification when batch has COMPLETED_WITH_PARTIAL_SUCCESS."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["ai_feedback"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS.value,
                    "essay_counts": {
                        "total": 5,
                        "pending_dispatch_or_processing": 0,
                        "successful": 3,
                        "failed": 2
                    },
                    "started_at": "2023-01-01T10:00:00Z",
                    "completed_at": "2023-01-01T10:45:00Z",
                    "error_info": {"failed_essays": ["essay-4", "essay-5"]},
                    "progress_percentage": 100.0
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:45:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert "ai_feedback processing has started" in reason

    async def test_cannot_modify_wrong_user(self, validator, mock_session):
        """Test validation blocks access for wrong user."""
        json_data = {
            "user_id": "other-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.PENDING_DEPENDENCIES.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert "You don't own this batch" in reason

    async def test_batch_not_found(self, validator, mock_session):
        """Test handling of non-existent batch."""
        self._setup_mock_response(mock_session, 404, {})

        can_modify, reason = await validator.can_modify_batch_files("nonexistent", "test-user")

        assert can_modify is False
        assert reason == "Batch not found"

    async def test_bos_server_error(self, validator, mock_session):
        """Test handling of BOS server errors."""
        self._setup_mock_response(mock_session, 500, {})

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert reason == "Unable to verify batch state"

    async def test_network_error_handling(self, validator, mock_session):
        """Test handling of network errors."""
        mock_session.get.side_effect = Exception("Network error")

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert reason == "Unable to verify batch state"

    async def test_invalid_pipeline_state_format(self, validator, mock_session):
        """Test handling of invalid pipeline state format."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                # Invalid structure that will cause Pydantic validation to fail
                "invalid_field": "invalid_value"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        can_modify, reason = await validator.can_modify_batch_files("batch-123", "test-user")

        assert can_modify is False
        assert reason == "Invalid pipeline state format"

    async def test_get_batch_lock_status_unlocked(self, validator, mock_session):
        """Test get_batch_lock_status returns correct status for unlocked batch."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.PENDING_DEPENDENCIES.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        lock_status = await validator.get_batch_lock_status("batch-123")

        assert lock_status["locked"] is False
        assert lock_status["reason"] == "Batch is open for modifications"
        assert lock_status["current_state"] == "READY_FOR_MODIFICATIONS"

    async def test_get_batch_lock_status_locked(self, validator, mock_session):
        """Test get_batch_lock_status returns correct status for locked batch."""
        json_data = {
            "user_id": "test-user",
            "pipeline_state": {
                "batch_id": "batch-123",
                "requested_pipelines": ["spellcheck"],
                "spellcheck": {
                    "status": PipelineExecutionStatus.IN_PROGRESS.value,
                    "essay_counts": {
                        "total": 5,
                        "pending_dispatch_or_processing": 3,
                        "successful": 2,
                        "failed": 0
                    },
                    "started_at": "2023-01-01T10:00:00Z",
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": 40.0
                },
                "cj_assessment": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "ai_feedback": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "nlp_metrics": {
                    "status": PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG.value,
                    "essay_counts": {
                        "total": 0,
                        "pending_dispatch_or_processing": 0,
                        "successful": 0,
                        "failed": 0
                    },
                    "started_at": None,
                    "completed_at": None,
                    "error_info": None,
                    "progress_percentage": None
                },
                "last_updated": "2023-01-01T10:00:00Z"
            }
        }
        self._setup_mock_response(mock_session, 200, json_data)

        lock_status = await validator.get_batch_lock_status("batch-123")

        assert lock_status["locked"] is True
        assert lock_status["reason"] == "spellcheck processing has started"
        assert lock_status["current_phase"] == "spellcheck"
        assert lock_status["phase_status"] == PipelineExecutionStatus.IN_PROGRESS.value
        assert lock_status["locked_at"] in ["2023-01-01T10:00:00Z", "2023-01-01T10:00:00+00:00"]
