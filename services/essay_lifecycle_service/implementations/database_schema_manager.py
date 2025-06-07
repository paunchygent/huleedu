"""
Database schema management for Essay Lifecycle Service SQLite implementation.

Handles schema initialization, migrations, and database structure management
for the SQLite-based persistence layer.
"""

from __future__ import annotations

import aiosqlite


class SQLiteDatabaseSchemaManager:
    """
    Manages SQLite database schema initialization and migrations.

    Responsible for creating tables, indexes, and managing schema versioning
    for the Essay Lifecycle Service SQLite persistence layer.
    """

    def __init__(self, database_path: str, timeout: float = 30.0) -> None:
        """
        Initialize the schema manager.

        Args:
            database_path: Path to the SQLite database file
            timeout: Database operation timeout in seconds
        """
        self.database_path = database_path
        self.timeout = timeout

    async def initialize_schema(self) -> None:
        """Initialize the database schema and migrations."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            # Enable foreign keys
            await db.execute("PRAGMA foreign_keys = ON")

            # Create schema version table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create essay_states table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS essay_states (
                    essay_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    current_status TEXT NOT NULL,
                    processing_metadata TEXT NOT NULL DEFAULT '{}',
                    timeline TEXT NOT NULL DEFAULT '{}',
                    storage_references TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)

            # Create index for batch queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_essay_states_batch_id
                ON essay_states(batch_id)
            """)

            # Create index for status queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_essay_states_status
                ON essay_states(current_status)
            """)

            # Set current schema version
            await db.execute("""
                INSERT OR IGNORE INTO schema_version (version) VALUES (1)
            """)

            await db.commit()
