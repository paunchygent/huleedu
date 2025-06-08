"""
Shared utilities for core logic validation integration tests.

Provides common imports and test constants used across
all validation integration test modules. Fixtures are defined in conftest.py.
"""

from __future__ import annotations

# Test constants
TEST_BATCH_IDS = {
    "success": "test_batch_123",
    "validation_failure": "test_batch_456",
    "empty_content": "test_batch_empty",
    "too_long": "test_batch_long",
    "extraction_failure": "test_batch_extract_fail",
    "storage_failure": "test_batch_storage_fail",
    "correlation": "test_batch_correlation",
    "fail_correlation": "test_batch_fail_correlation",
    "empty_success": "test_batch_empty_success"
}

TEST_FILE_NAMES = {
    "valid": "essay1.txt",
    "empty": "empty_essay.txt",
    "long": "very_long_essay.txt",
    "extraction_fail": "corrupted_file.pdf",
    "storage_fail": "valid_essay.txt",
    "correlation": "correlation_test.txt",
    "fail_correlation": "short_essay.txt",
    "empty_success": "empty.txt"
}

VALID_FILE_CONTENT = b"Valid essay content for testing"
EMPTY_FILE_CONTENT = b"Empty"
ZERO_BYTE_CONTENT = b""
