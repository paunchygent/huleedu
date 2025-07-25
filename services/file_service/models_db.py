"""
Database models for File Service.

This module contains SQLAlchemy models for the File Service database.
Currently, the File Service primarily uses the event outbox pattern,
but this module can be extended with domain-specific models as needed.
"""

from __future__ import annotations

from sqlalchemy.ext.declarative import declarative_base

# Create a Base for File Service models
Base = declarative_base()

# File Service currently doesn't have domain-specific models
# as it's primarily a stateless file processing service.
# The event outbox table is provided by the shared library.
# 
# Future models could include:
# - FileProcessingHistory: Track processed files
# - FileMetadata: Store additional file information
# - ProcessingStats: Track processing metrics