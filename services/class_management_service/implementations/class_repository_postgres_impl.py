from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Type, TypeVar, cast

from huleedu_service_libs.database import DatabaseMetricsProtocol
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
)
from services.class_management_service.protocols import (
    ClassRepositoryProtocol,
)
from services.class_management_service.exceptions import (
    CourseNotFoundError,
    MultipleCourseError,
)
from common_core.domain_enums import CourseCode

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
        self, user_id: str, class_data: CreateClassRequest
    ) -> T:  # Returns type T (UserClass or subclass)
        start_time = time.time()
        operation = "create_class"
        table = "user_classes"
        success = True

        try:
            async with self.session() as session:
                # Validate course codes
                course = await self._validate_and_get_course(
                    session, class_data.course_codes
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
                .options(
                    selectinload(UserClass.students),
                    selectinload(UserClass.course)
                )
            )
            result = await session.execute(stmt)
            return cast(T | None, result.scalars().first())

    async def update_class(
        self, class_id: uuid.UUID, class_data: UpdateClassRequest
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
                    session, class_data.course_codes
                )
                db_class.course = course

            await session.flush()
            return cast(T, db_class)

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        async with self.session() as session:
            stmt = delete(UserClass).where(UserClass.id == class_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def create_student(
        self, user_id: str, student_data: CreateStudentRequest
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
                
                if student_data.class_ids:
                    stmt = select(UserClass).where(UserClass.id.in_(student_data.class_ids))
                    result = await session.execute(stmt)
                    classes = result.scalars().all()
                    new_student.classes.extend(classes)
                
                await session.flush()
                
                # CRITICAL: Eager load classes relationship before session closes
                await session.refresh(new_student, ['classes'])
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
                        selectinload(Student.classes),
                        selectinload(Student.essay_associations)
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
        self, student_id: uuid.UUID, student_data: UpdateStudentRequest
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
                        selectinload(Student.classes),
                        selectinload(Student.essay_associations)
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
                    class_stmt = select(UserClass).where(UserClass.id.in_(student_data.add_class_ids))
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
                stmt = delete(Student).where(Student.id == student_id)
                result = await session.execute(stmt)
                return result.rowcount > 0

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to delete student: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def associate_essay_to_student(
        self, user_id: str, essay_id: uuid.UUID, student_id: uuid.UUID
    ) -> None:
        start_time = time.time()
        operation = "associate_essay_to_student"
        table = "essay_student_associations"
        success = True

        try:
            async with self.session() as session:
                association = EssayStudentAssociation(
                    essay_id=essay_id, student_id=student_id, created_by_user_id=user_id
                )
                session.add(association)
                await session.flush()

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            self._record_error_metrics(error_type, operation)
            logger.error(f"Failed to associate essay to student: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time
            self._record_operation_metrics(operation, table, duration, success)

    async def _validate_and_get_course(
        self, session: AsyncSession, course_codes: list[CourseCode]
    ) -> Course:
        """Validate course codes and return the single course.
        
        Args:
            session: Database session
            course_codes: List of course codes to validate
            
        Returns:
            The validated Course entity
            
        Raises:
            MultipleCourseError: If multiple course codes are provided
            CourseNotFoundError: If the course code is not found in the database
        """
        if len(course_codes) > 1:
            raise MultipleCourseError(course_codes)
        
        if not course_codes:
            # This should be caught by Pydantic validation, but defensive programming
            raise CourseNotFoundError([])
        
        course_code = course_codes[0]
        
        stmt = select(Course).where(Course.course_code == course_code)
        result = await session.execute(stmt)
        course = result.scalars().first()
        
        if course is None:
            raise CourseNotFoundError([course_code])
        
        return course
