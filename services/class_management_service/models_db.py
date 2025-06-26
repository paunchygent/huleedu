from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from common_core.domain_enums import CourseCode, Language
from common_core.metadata_models import PersonNameV1


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class_student_association = Table(
    "class_student_association",
    Base.metadata,
    Column("class_id", UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE")),
    Column("student_id", UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE")),
)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    course_code: Mapped[CourseCode] = mapped_column(
        SQLAlchemyEnum(
            CourseCode,
            name="course_code_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[Language] = mapped_column(
        SQLAlchemyEnum(
            Language,
            name="language_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=Language.SWEDISH,
    )
    skill_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    classes: Mapped[list["UserClass"]] = relationship(back_populates="course")


class UserClass(Base):
    __tablename__ = "classes"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    course: Mapped["Course"] = relationship(back_populates="classes")
    students: Mapped[list["Student"]] = relationship(
        secondary=class_student_association, back_populates="classes"
    )


class Student(Base):
    __tablename__ = "students"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # PersonNameV1 Fields
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # End PersonNameV1 Fields
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    classes: Mapped[list["UserClass"]] = relationship(
        secondary=class_student_association, back_populates="students"
    )
    essay_associations: Mapped[list["EssayStudentAssociation"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("email", "created_by_user_id", name="uix_student_email_user"),
    )

    def to_person_name_v1(self) -> PersonNameV1:
        return PersonNameV1(
            first_name=self.first_name,
            last_name=self.last_name,
            legal_full_name=self.legal_full_name,
        )


class EssayStudentAssociation(Base):
    __tablename__ = "essay_student_associations"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    essay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, unique=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))

    student: Mapped["Student"] = relationship(back_populates="essay_associations")
