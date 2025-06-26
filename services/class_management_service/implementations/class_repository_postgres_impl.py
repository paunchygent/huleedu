from __future__ import annotations

import uuid
from typing import Type, TypeVar, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
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

# Define concrete types for this implementation
T = TypeVar('T', bound=UserClass)
U = TypeVar('U', bound=Student)


class PostgreSQLClassRepositoryImpl(ClassRepositoryProtocol[T, U]):
    """PostgreSQL implementation of ClassRepositoryProtocol with generic types."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Store the actual model classes
        self._user_class_type: Type[T] = cast(Type[T], UserClass)
        self._student_type: Type[U] = cast(Type[U], Student)

    async def create_class(
        self, user_id: str, class_data: CreateClassRequest
    ) -> T:  # Returns type T (UserClass or subclass)
        # In a real app, you'd look up the courses or create them
        # Here we assume they exist for simplicity
        stmt = select(Course).where(Course.course_code.in_(class_data.course_codes))
        result = await self.session.execute(stmt)
        courses = result.scalars().all()

        new_class = UserClass(
            name=class_data.name,
            created_by_user_id=user_id,
            # For simplicity, associating with the first course found
            course=courses[0] if courses else None,
        )
        self.session.add(new_class)
        await self.session.flush()
        return cast(T, new_class)

    async def get_class_by_id(self, class_id: uuid.UUID) -> T | None:  # Returns type T or None
        stmt = (
            select(UserClass)
            .where(UserClass.id == class_id)
            .options(selectinload(UserClass.students))
        )
        result = await self.session.execute(stmt)
        return cast(T | None, result.scalars().first())

    async def update_class(
        self, class_id: uuid.UUID, class_data: UpdateClassRequest
    ) -> T | None:  # Returns type T or None
        # Implementation would go here
        pass

    async def delete_class(self, class_id: uuid.UUID) -> bool:
        stmt = delete(UserClass).where(UserClass.id == class_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def create_student(
        self, user_id: str, student_data: CreateStudentRequest
    ) -> U:  # Returns type U (Student or subclass)
        new_student = Student(
            first_name=student_data.person_name.first_name,
            last_name=student_data.person_name.last_name,
            legal_full_name=student_data.person_name.legal_full_name,
            email=student_data.email,
            created_by_user_id=user_id,
        )
        self.session.add(new_student)
        await self.session.flush()

        if student_data.class_ids:
            stmt = select(UserClass).where(UserClass.id.in_(student_data.class_ids))
            result = await self.session.execute(stmt)
            classes = result.scalars().all()
            new_student.classes.extend(classes)

        return cast(U, new_student)

    async def get_student_by_id(self, student_id: uuid.UUID) -> U | None:  # Returns type U or None
        stmt = (
            select(Student)
            .where(Student.id == student_id)
            .options(selectinload(Student.classes))
        )
        result = await self.session.execute(stmt)
        return cast(U | None, result.scalars().first())

    async def update_student(
        self, student_id: uuid.UUID, student_data: UpdateStudentRequest
    ) -> U | None:  # Returns type U or None
        # Implementation would go here
        pass

    async def delete_student(self, student_id: uuid.UUID) -> bool:
        stmt = delete(Student).where(Student.id == student_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def associate_essay_to_student(
        self, user_id: str, essay_id: uuid.UUID, student_id: uuid.UUID
    ) -> None:
        association = EssayStudentAssociation(
            essay_id=essay_id, student_id=student_id, created_by_user_id=user_id
        )
        self.session.add(association)
        await self.session.flush()
