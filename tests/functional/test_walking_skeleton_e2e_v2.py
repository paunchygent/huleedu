"""
DEPRECATED: This file has been split into modular components for better maintainability.

The original Walking Skeleton e2e tests (561 lines) have been refactored into focused modules:

Shared utilities and configuration:
- walking_skeleton_e2e_utils.py (145 lines) - Common imports, configuration, and EventCollector

Test modules by functionality:
- test_walking_skeleton_architecture_fix.py (304 lines) - Main architecture fix validation workflow
- test_walking_skeleton_excess_content.py (95 lines) - Excess content handling validation

This modular structure follows Single Responsibility Principle (SRP) and maintains
all tests under the 400-line limit while preserving 100% test coverage.

Run individual test modules:
- pdm run pytest tests/functional/test_walking_skeleton_architecture_fix.py
- pdm run pytest tests/functional/test_walking_skeleton_excess_content.py

Run all walking skeleton tests:
- pdm run pytest tests/functional/test_walking_skeleton_*.py
"""

# This file is intentionally empty - use the modular split files above
