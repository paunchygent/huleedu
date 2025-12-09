from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional, Type, TypeVar, cast
from uuid import UUID

from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.database import DatabaseMetricsProtocol
from huleedu_service_libs.error_handling import (
    raise_course_not_found,
    raise_multiple_course_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.models_db import (
    Course,
    EssayStudentAssociation,
    Student,
    UserClass,
    class_student_association,
)
from services.class_management_service.protocols import (
    ClassRepositoryProtocol,
)

logger = create_service_logger("class_management_service.repository")

# Define concrete types for this implementation
T = TypeVar("T", bound=UserClass)
U = TypeVar("U", bound=Student)


class PostgreSQLClassRepositoryImpl(ClassRepositoryProtocol[T, U]):
    """PostgreSQL implementation of ClassRepositoryProtocol with
    generic types and database metrics."""

    def __init__(
        self, engine: AsyncEngine, metrics: Optional[DatabaseMetricsProtocol] = None
    ) -> None:
        self.engine = engine
        self.metrics = metrics
        self.async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
        # Store the actual model classes
        self._user_class_type: Type[T] = cast(Type[T], UserClass)
        self._student_type: Type[U] = cast(Type[U], Student)

    def _record_operation_metrics(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record database operation metrics."""
        if self.metrics:
            self.metrics.record_query_duration(
                operation=operation,
                table=table,
                duration=duration,
                success=success,
            )

    def _record_error_metrics(self, error_type: str, operation: str) -> None:
        """Record database error metrics."""
        if self.metrics:
            self.metrics.record_database_error(error_type, operation)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional session context."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_class(
        self, user_id: str, class_data: CreateClassRequest, correlation_id: UUID
    ) -> T:  # Returns type T (UserClass or subclass)
        start_time = time.time()
        operation = "create_class"
        table = "user_classes"
        success = True

        try:
            async with self.session() as session:
                # Validate course codes
                course = await self._validate_and_get_course(
                    session, class_data.course_codes, correlation_id
                )

                new_class = UserClass(
                    name=class_data.name,
                    created_by_user_id=user_id,
                    course=course,
                )
                session.add(new_class)
                await session.flush()
                return cast(T, new_class)

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to create class: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:  # Returns type T or None
        async with self.session() as session:
            stmt = (
                select(UserClass)
                .where(UserClass.id == class_id)
                .options(selectinload(UserClass.students), selectinload(UserClass.course))
            )
            result = await session.execute(stmt)
            return cast(T | None, result.scalars().first())

    async def update_class(
        self, class_id: uuid.UUID, class_data: UpdateClassRequest, correlation_id: UUID
    ) -> T | None:  # Returns type T or None
        async with self.session() as session:
            stmt = select(UserClass).where(UserClass.id == class_id)
            result = await session.execute(stmt)
            db_class = result.scalars().first()

            if not db_class:
                return None

            if class_data.name is not None:
                db_class.name = class_data.name

            if class_data.course_codes is not None:
                # Validate course codes and get the single course
                course = await self._validate_and_get_course(
                    session, class_data.course_codes, correlation_id
                )
                db_class.course = course

            await session.flush()
            return cast(T, db_class)

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        async with self.session() as session:
            stmt = delete(UserClass).where(UserClass.id == class_id).returning(UserClass.id)
            result = await session.execute(stmt)
            deleted_ids = result.scalars().all()
            return bool(deleted_ids)

    async def create_student(
        self, user_id: str, student_data: CreateStudentRequest, correlation_id: UUID
    ) -> U:  # Returns type U (Student or subclass)
        start_time = time.time()
        operation = "create_student"
        table = "students"
        success = True

        try:
            async with self.session() as session:
                new_student = Student(
                    first_name=student_data.person_name.first_name,
                    last_name=student_data.person_name.last_name,
                    legal_full_name=student_data.person_name.legal_full_name,
                    email=student_data.email,
                    created_by_user_id=user_id,
                )
                session.add(new_student)

                # Flush first to get the student ID
                await session.flush()

                if student_data.class_ids:
                    # Use raw SQL to insert associations to avoid lazy loading issues
                    for class_id in student_data.class_ids:
                        association_stmt = class_student_association.insert().values(
                            class_id=class_id, student_id=new_student.id
                        )
                        await session.execute(association_stmt)

                # CRITICAL: Eager load classes relationship before session closes
                await session.refresh(new_student, ["classes"])
                return cast(U, new_student)

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to create student: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:  # Returns type U or None
        start_time = time.time()
        operation = "get_student_by_id"
        table = "students"
        success = True

        try:
            async with self.session() as session:
                stmt = (
                    select(Student)
                    .where(Student.id == student_id)
                    .options(
                        selectinload(Student.classes), selectinload(Student.essay_associations)
                    )
                )
                result = await session.execute(stmt)
                return cast(U | None, result.scalars().first())

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to get student by id: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def update_student(
        self, student_id: uuid.UUID, student_data: UpdateStudentRequest, correlation_id: UUID
    ) -> U | None:  # Returns type U or None
        start_time = time.time()
        operation = "update_student"
        table = "students"
        success = True

        try:
            async with self.session() as session:
                stmt = (
                    select(Student)
                    .where(Student.id == student_id)
                    .options(
                        selectinload(Student.classes), selectinload(Student.essay_associations)
                    )
                )
                result = await session.execute(stmt)
                db_student = result.scalars().first()

                if not db_student:
                    return None

                if student_data.person_name:
                    db_student.first_name = student_data.person_name.first_name
                    db_student.last_name = student_data.person_name.last_name
                    db_student.legal_full_name = student_data.person_name.legal_full_name

                if student_data.email is not None:
                    db_student.email = student_data.email

                if student_data.add_class_ids:
                    class_stmt = select(UserClass).where(
                        UserClass.id.in_(student_data.add_class_ids)
                    )
                    class_result = await session.execute(class_stmt)
                    classes_to_add = class_result.scalars().all()
                    for cls in classes_to_add:
                        if cls not in db_student.classes:
                            db_student.classes.append(cls)

                if student_data.remove_class_ids:
                    db_student.classes = [
                        c for c in db_student.classes if c.id not in student_data.remove_class_ids
                    ]

                await session.flush()
                return cast(U, db_student)

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to update student: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def delete_student(self, student_id: uuid.UUID) -> bool:
        start_time = time.time()
        operation = "delete_student"
        table = "students"
        success = True

        try:
            async with self.session() as session:
                stmt = delete(Student).where(Student.id == student_id).returning(Student.id)
                result = await session.execute(stmt)
                deleted_ids = result.scalars().all()
                return bool(deleted_ids)

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to delete student: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_batch_student_associations(self, batch_id: UUID) -> list[Any]:
        """Get all student-essay associations for a batch."""
        start_time = time.time()
        operation = "get_batch_student_associations"
        table = "essay_student_associations"
        success = True

        try:
            async with self.session() as session:
                # Query associations by batch_id
                stmt = (
                    select(EssayStudentAssociation)
                    .join(Student)
                    .where(EssayStudentAssociation.batch_id == batch_id)
                    .order_by(EssayStudentAssociation.created_at.desc())
                )
                result = await session.execute(stmt)
                associations = result.scalars().all()
                return list(associations)

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to get batch student associations: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_batch_student_names(
        self, batch_id: UUID, correlation_id: UUID
    ) -> list[dict[str, Any]]:
        """Get all student names for essays in a batch with PersonNameV1 structure.

        Args:
            batch_id: The batch ID to query
            correlation_id: Request correlation ID for observability

        Returns:
            List of dictionaries with essay_id, student_id, student_person_name
        """
        start_time = time.time()
        operation = "get_batch_student_names"
        table = "essay_student_associations"
        success = True

        try:
            async with self.session() as session:
                # JOIN query to get essay associations with student names
                stmt = (
                    select(
                        EssayStudentAssociation.essay_id,
                        EssayStudentAssociation.student_id,
                        Student.first_name,
                        Student.last_name,
                        Student.legal_full_name,
                    )
                    .join(Student, EssayStudentAssociation.student_id == Student.id)
                    .where(EssayStudentAssociation.batch_id == batch_id)
                    .order_by(EssayStudentAssociation.created_at.desc())
                )

                result = await session.execute(stmt)
                rows = result.all()

                # Convert to expected format with PersonNameV1
                batch_names = []
                for row in rows:
                    # Create PersonNameV1 compatible structure
                    person_name = PersonNameV1(
                        first_name=row.first_name or "",
                        last_name=row.last_name or "",
                        legal_full_name=row.legal_full_name,
                    )

                    batch_names.append(
                        {
                            "essay_id": row.essay_id,
                            "student_id": row.student_id,
                            "student_person_name": person_name,
                        }
                    )

                logger.info(
                    f"Retrieved {len(batch_names)} student names for batch",
                    extra={
                        "batch_id": str(batch_id),
                        "count": len(batch_names),
                        "correlation_id": str(correlation_id),
                    },
                )

                return batch_names

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(
                f"Failed to get batch student names: {error_type}: {e}",
                extra={
                    "batch_id": str(batch_id),
                    "correlation_id": str(correlation_id),
                },
            )
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_essay_student_association(
        self, essay_id: UUID, correlation_id: UUID
    ) -> dict[str, Any] | None:
        """Get student association for a single essay with PersonNameV1 structure.

        Args:
            essay_id: The essay ID to query
            correlation_id: Request correlation ID for observability

        Returns:
            Dictionary with essay_id, student_id, student_person_name, or None if not found
        """
        start_time = time.time()
        operation = "get_essay_student_association"
        table = "essay_student_associations"
        success = True

        try:
            async with self.session() as session:
                # JOIN query to get single essay association with student name
                stmt = (
                    select(
                        EssayStudentAssociation.essay_id,
                        EssayStudentAssociation.student_id,
                        Student.first_name,
                        Student.last_name,
                        Student.legal_full_name,
                    )
                    .join(Student, EssayStudentAssociation.student_id == Student.id)
                    .where(EssayStudentAssociation.essay_id == essay_id)
                )

                result = await session.execute(stmt)
                row = result.first()

                if not row:
                    logger.info(
                        "No student association found for essay",
                        extra={
                            "essay_id": str(essay_id),
                            "correlation_id": str(correlation_id),
                        },
                    )
                    return None

                # Create PersonNameV1 compatible structure
                person_name = PersonNameV1(
                    first_name=row.first_name or "",
                    last_name=row.last_name or "",
                    legal_full_name=row.legal_full_name,
                )

                association = {
                    "essay_id": row.essay_id,
                    "student_id": row.student_id,
                    "student_person_name": person_name,
                }

                logger.info(
                    "Retrieved student association for essay",
                    extra={
                        "essay_id": str(essay_id),
                        "student_id": str(row.student_id),
                        "correlation_id": str(correlation_id),
                    },
                )

                return association

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(
                f"Failed to get essay student association: {error_type}: {e}",
                extra={
                    "essay_id": str(essay_id),
                    "correlation_id": str(correlation_id),
                },
            )
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def list_classes_by_owner(self, user_id: str, limit: int, offset: int) -> list[T]:
        """List classes created by a specific user with related course and students preloaded."""
        start_time = time.time()
        operation = "list_classes_by_owner"
        table = "classes"
        success = True

        try:
            async with self.session() as session:
                stmt = (
                    select(UserClass)
                    .where(UserClass.created_by_user_id == user_id)
                    .options(selectinload(UserClass.course), selectinload(UserClass.students))
                    .order_by(UserClass.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                result = await session.execute(stmt)
                classes = result.scalars().all()
                return cast(list[T], list(classes))

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(
                f"Failed to list classes by owner: {error_type}: {e}",
                extra={"user_id": user_id, "limit": limit, "offset": offset},
            )
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def get_class_info_for_batches(
        self, batch_ids: list[UUID]
    ) -> dict[str, dict[str, str] | None]:
        """Get class info for multiple batches via EssayStudentAssociation.

        Args:
            batch_ids: List of batch UUIDs to look up

        Returns:
            Dict mapping batch_id (str) to class info dict or None if no association.
        """
        start_time = time.time()
        operation = "get_class_info_for_batches"
        table = "essay_student_associations"
        success = True

        try:
            async with self.session() as session:
                # Build result dict with None defaults for all requested batch_ids
                result: dict[str, dict[str, str] | None] = {str(bid): None for bid in batch_ids}

                if not batch_ids:
                    return result

                # Query distinct batch_id -> class info via EssayStudentAssociation
                stmt = (
                    select(
                        EssayStudentAssociation.batch_id,
                        UserClass.id,
                        UserClass.name,
                    )
                    .join(UserClass, EssayStudentAssociation.class_id == UserClass.id)
                    .where(EssayStudentAssociation.batch_id.in_(batch_ids))
                    .distinct(EssayStudentAssociation.batch_id)
                )
                rows = await session.execute(stmt)

                for batch_id, class_id, class_name in rows.all():
                    result[str(batch_id)] = {
                        "class_id": str(class_id),
                        "class_name": class_name,
                    }

                logger.info(
                    f"Retrieved class info for {len(batch_ids)} batches",
                    extra={
                        "requested_count": len(batch_ids),
                        "found_count": sum(1 for v in result.values() if v is not None),
                    },
                )

                return result

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to get class info for batches: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def _validate_and_get_course(
        self, session: AsyncSession, course_codes: list[CourseCode], correlation_id: UUID
    ) -> Course:
        """Validate course codes and return the single course.

        Args:
            session: Database session
            course_codes: List of course codes to validate
            correlation_id: Request correlation ID for tracking

        Returns:
            The validated Course entity

        Raises:
            HuleEduError: If validation fails or course not found
        """
        if len(course_codes) > 1:
            course_codes_str = ", ".join(code.value for code in course_codes)
            raise_multiple_course_error(
                service="class_management_service",
                operation="_validate_and_get_course",
                message=(
                    f"Multiple courses provided ({course_codes_str}), "
                    f"but only one course per class is supported"
                ),
                correlation_id=correlation_id,
                provided_course_codes=[code.value for code in course_codes],
            )

        if not course_codes:
            # This should be caught by Pydantic validation, but defensive programming
            raise_validation_error(
                service="class_management_service",
                operation="_validate_and_get_course",
                field="course_codes",
                message="Course codes list cannot be empty",
                correlation_id=correlation_id,
            )

        course_code = course_codes[0]

        stmt = select(Course).where(Course.course_code == course_code)
        result = await session.execute(stmt)
        course = result.scalars().first()

        if course is None:
            raise_course_not_found(
                service="class_management_service",
                operation="_validate_and_get_course",
                course_id=str(course_code.value),
                correlation_id=correlation_id,
                missing_course_codes=[course_code.value],
            )

        return course
