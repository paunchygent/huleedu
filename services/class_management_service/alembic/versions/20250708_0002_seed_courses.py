"""Seed courses table with predefined CourseCode enum values

Revision ID: 0002
Revises: 0001
Create Date: 2025-07-08 10:00:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed courses table with predefined CourseCode enum values."""
    # Define enum types to match database schema
    course_code_enum = postgresql.ENUM(
        "ENG5", "ENG6", "ENG7", "SV1", "SV2", "SV3", name="course_code_enum", create_type=False
    )
    language_enum = postgresql.ENUM("en", "sv", name="language_enum", create_type=False)

    # Create courses table reference for bulk insert
    courses_table = sa.table(
        "courses",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("course_code", course_code_enum),
        sa.column("name", sa.String),
        sa.column("language", language_enum),
        sa.column("skill_level", sa.Integer),
    )

    # Course metadata mapping (course_code -> (name, language, skill_level))
    course_data = [
        ("ENG5", "English 5", "en", 5),
        ("ENG6", "English 6", "en", 6),
        ("ENG7", "English 7", "en", 7),
        ("SV1", "Svenska 1", "sv", 1),
        ("SV2", "Svenska 2", "sv", 2),
        ("SV3", "Svenska 3", "sv", 3),
    ]

    # Insert predefined courses
    for course_code, name, language, skill_level in course_data:
        op.execute(
            courses_table.insert().values(
                id=uuid.uuid4(),
                course_code=course_code,
                name=name,
                language=language,
                skill_level=skill_level,
            )
        )


def downgrade() -> None:
    """Remove seeded courses."""
    # Delete all courses (this will cascade to any dependent classes)
    op.execute("DELETE FROM courses")
