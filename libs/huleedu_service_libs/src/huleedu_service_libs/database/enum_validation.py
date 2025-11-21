"""Helpers to validate Postgres enums against Python Enum definitions."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class EnumDriftError(RuntimeError):
    """Raised when a database enum is missing required values."""


async def assert_enum_contains(
    engine: AsyncEngine,
    enum_name: str,
    expected_values: Iterable[str],
    *,
    service_name: str | None = None,
) -> None:
    """Validate that the DB enum contains all expected values.

    Allows DB to be a superset (legacy values are tolerated). Raises EnumDriftError
    if any Python enum values are missing in the database.
    """

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                SELECT enumlabel
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = :enum_name
                ORDER BY enumsortorder
                """
            ),
            {"enum_name": enum_name},
        )
        db_values = set(rows.scalars())

    missing = set(expected_values) - db_values
    if missing:
        context = f" for {service_name}" if service_name else ""
        raise EnumDriftError(
            f"Database enum '{enum_name}' is missing values {sorted(missing)}{context}. "
            "Add an Alembic migration to align database types with Python enums."
        )
