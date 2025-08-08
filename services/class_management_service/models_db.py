from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from common_core.domain_enums import CourseCode, Language
from common_core.metadata_models import PersonNameV1
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    classes: Mapped[list["UserClass"]] = relationship(back_populates="course")


class UserClass(Base):
    __tablename__ = "classes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    essay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, unique=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))

    # Add new fields from the task plan
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reasons: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_validation"
    )
    validated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validation_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    student: Mapped["Student"] = relationship(back_populates="essay_associations")
    user_class: Mapped["UserClass"] = relationship()


class EventOutbox(Base):
    """
    Generic event outbox table for reliable event publishing.

    This table stores events that need to be published to Kafka, ensuring
    that database updates and event publications are atomic. Events are
    written to this table in the same transaction as business logic updates.

    The event relay worker polls this table and publishes events to Kafka,
    marking them as published upon success.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Aggregate information
    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Event information
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    event_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Kafka targeting
    topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Kafka topic to publish to",
    )

    # Publishing state
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Retry handling
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Indexes for performance
    __table_args__ = (
        # Index for polling unpublished events efficiently with topic filtering
        Index(
            "ix_event_outbox_unpublished_topic",
            "published_at",
            "topic",
            "created_at",
            postgresql_where="published_at IS NULL",
        ),
        # Index for filtering by topic
        Index(
            "ix_event_outbox_topic",
            "topic",
        ),
        # Index for looking up events by aggregate
        Index(
            "ix_event_outbox_aggregate",
            "aggregate_type",
            "aggregate_id",
        ),
        # Index for monitoring/debugging by event type
        Index(
            "ix_event_outbox_event_type",
            "event_type",
        ),
    )
