"""Initial schema migration for Class Management Service

Revision ID: 0001
Revises:
Create Date: 2025-07-06 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema for Class Management Service."""
    # Create ENUM types
    course_code_enum = postgresql.ENUM(
        "ENG5", "ENG6", "ENG7", "SV1", "SV2", "SV3", name="course_code_enum"
    )
    course_code_enum.create(op.get_bind(), checkfirst=True)

    language_enum = postgresql.ENUM("en", "sv", name="language_enum")
    language_enum.create(op.get_bind(), checkfirst=True)

    # Create courses table
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "course_code",
            course_code_enum,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "language",
            language_enum,
            nullable=False,
            server_default="sv",
        ),
        sa.Column("skill_level", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_code"),
    )

    # Create classes table
    op.create_table(
        "classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create index on created_by_user_id for classes
    op.create_index(op.f("ix_classes_created_by_user_id"), "classes", ["created_by_user_id"])

    # Create students table
    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.Column("legal_full_name", sa.String(length=512), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "created_by_user_id", name="uix_student_email_user"),
    )

    # Create index on created_by_user_id for students
    op.create_index(op.f("ix_students_created_by_user_id"), "students", ["created_by_user_id"])

    # Create essay_student_associations table
    op.create_table(
        "essay_student_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("essay_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("essay_id"),
    )

    # Create indexes for essay_student_associations
    op.create_index(
        op.f("ix_essay_student_associations_essay_id"),
        "essay_student_associations",
        ["essay_id"],
    )
    op.create_index(
        op.f("ix_essay_student_associations_created_by_user_id"),
        "essay_student_associations",
        ["created_by_user_id"],
    )

    # Create class_student_association table (many-to-many relationship)
    op.create_table(
        "class_student_association",
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    """Drop all Class Management Service tables and types."""
    # Drop tables in reverse order of dependencies
    op.drop_table("class_student_association")
    op.drop_index(
        op.f("ix_essay_student_associations_created_by_user_id"),
        table_name="essay_student_associations",
    )
    op.drop_index(
        op.f("ix_essay_student_associations_essay_id"),
        table_name="essay_student_associations",
    )
    op.drop_table("essay_student_associations")
    op.drop_index(op.f("ix_students_created_by_user_id"), table_name="students")
    op.drop_table("students")
    op.drop_index(op.f("ix_classes_created_by_user_id"), table_name="classes")
    op.drop_table("classes")
    op.drop_table("courses")

    # Drop ENUM types
    course_code_enum = postgresql.ENUM(name="course_code_enum")
    course_code_enum.drop(op.get_bind())

    language_enum = postgresql.ENUM(name="language_enum")
    language_enum.drop(op.get_bind())
