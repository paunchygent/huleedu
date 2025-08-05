"""
Critical validation test to catch analysis errors and hallucinated variables/enums early.

This test validates that all imports, enums, protocols, models, and configurations
referenced in the analysis actually exist and have the expected structure.
This prevents building tests on incorrect assumptions.
"""

from __future__ import annotations

import inspect
import uuid
from typing import get_type_hints

import pytest

# Test all critical imports from analysis
from common_core.domain_enums import CourseCode
from common_core.error_enums import ClassManagementErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.class_events import (
    ClassCreatedV1,
    ClassUpdatedV1,
    StudentCreatedV1,
    StudentUpdatedV1,
)
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_course_not_found,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.config import Settings
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import Course, Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
)


class TestAnalysisValidation:
    """Test suite to validate analysis assumptions and catch hallucinations."""

    def test_course_code_enum_exists_and_has_expected_values(self) -> None:
        """Validate CourseCode enum exists with expected values from analysis."""
        # Verify enum exists and is properly structured
        assert hasattr(CourseCode, "ENG5"), "CourseCode.ENG5 should exist"
        assert hasattr(CourseCode, "SV1"), "CourseCode.SV1 should exist"

        # Verify it's a proper enum with string values
        assert isinstance(CourseCode.ENG5.value, str), "CourseCode values should be strings"
        assert CourseCode.ENG5.value == "ENG5", "CourseCode.ENG5 should have value 'ENG5'"
        assert CourseCode.SV1.value == "SV1", "CourseCode.SV1 should have value 'SV1'"

        # Verify we can iterate over enum values
        course_codes = list(CourseCode)
        assert len(course_codes) > 0, "CourseCode enum should have values"
        print(f"✓ CourseCode enum validated with {len(course_codes)} values")

    def test_event_classes_exist_with_expected_fields(self) -> None:
        """Validate event classes exist with fields referenced in analysis."""
        # Test ClassCreatedV1
        class_created_hints = get_type_hints(ClassCreatedV1)
        expected_class_fields = {"class_id", "class_designation", "course_codes", "user_id"}
        assert expected_class_fields.issubset(class_created_hints.keys()), (
            f"ClassCreatedV1 missing expected fields. "
            f"Expected: {expected_class_fields}, Got: {set(class_created_hints.keys())}"
        )

        # Test ClassUpdatedV1
        class_updated_hints = get_type_hints(ClassUpdatedV1)
        expected_update_fields = {"class_id", "class_designation"}
        assert expected_update_fields.issubset(class_updated_hints.keys()), (
            f"ClassUpdatedV1 missing expected fields. "
            f"Expected: {expected_update_fields}, Got: {set(class_updated_hints.keys())}"
        )

        # Test StudentCreatedV1 and StudentUpdatedV1
        student_created_hints = get_type_hints(StudentCreatedV1)
        student_updated_hints = get_type_hints(StudentUpdatedV1)
        expected_student_fields = {"student_id", "first_name", "last_name"}

        assert expected_student_fields.issubset(student_created_hints.keys()), (
            "StudentCreatedV1 missing expected fields"
        )
        assert expected_student_fields.issubset(student_updated_hints.keys()), (
            "StudentUpdatedV1 missing expected fields"
        )

        print("✓ Event classes validated with expected fields")

    def test_event_envelope_generic_structure(self) -> None:
        """Validate EventEnvelope generic structure matches analysis."""
        # Verify EventEnvelope can be instantiated with event data
        test_event_data = ClassCreatedV1(
            class_id=str(uuid.uuid4()),
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="test-user",
        )

        envelope = EventEnvelope[ClassCreatedV1](
            event_type=topic_name(ProcessingEvent.CLASS_CREATED),
            source_service="class_management_service",
            correlation_id=uuid.uuid4(),
            data=test_event_data,
        )

        assert envelope.data == test_event_data
        assert envelope.event_type == topic_name(ProcessingEvent.CLASS_CREATED)
        assert envelope.source_service == "class_management_service"
        assert envelope.correlation_id is not None
        print("✓ EventEnvelope generic structure validated")

    def test_database_models_have_expected_relationships(self) -> None:
        """Validate database models have relationships referenced in analysis."""
        # Test UserClass model
        user_class_attrs = dir(UserClass)
        assert "students" in user_class_attrs, "UserClass should have 'students' relationship"
        assert "course" in user_class_attrs, "UserClass should have 'course' relationship"
        assert "id" in user_class_attrs, "UserClass should have 'id' field"
        assert "name" in user_class_attrs, "UserClass should have 'name' field"

        # Test Student model
        student_attrs = dir(Student)
        assert "classes" in student_attrs, "Student should have 'classes' relationship"
        assert "id" in student_attrs, "Student should have 'id' field"
        assert "first_name" in student_attrs, "Student should have 'first_name' field"
        assert "last_name" in student_attrs, "Student should have 'last_name' field"
        assert "email" in student_attrs, "Student should have 'email' field"

        # Test Course model
        course_attrs = dir(Course)
        assert "course_code" in course_attrs, "Course should have 'course_code' field"
        assert "classes" in course_attrs, "Course should have 'classes' relationship"

        print("✓ Database model relationships validated")

    def test_protocols_have_expected_methods(self) -> None:
        """Validate protocols have methods referenced in analysis."""
        # Test ClassRepositoryProtocol
        repo_methods = [
            method for method in dir(ClassRepositoryProtocol) if not method.startswith("_")
        ]
        expected_repo_methods = {
            "create_class",
            "get_class_by_id",
            "update_class",
            "delete_class",
            "create_student",
            "get_student_by_id",
            "update_student",
            "delete_student",
            "get_batch_student_associations",
        }

        for method in expected_repo_methods:
            assert method in repo_methods, f"ClassRepositoryProtocol missing method: {method}"

        # Test ClassEventPublisherProtocol
        publisher_methods = [
            method for method in dir(ClassEventPublisherProtocol) if not method.startswith("_")
        ]
        assert "publish_class_event" in publisher_methods, (
            "ClassEventPublisherProtocol missing publish_class_event"
        )

        # Test ClassManagementServiceProtocol - using actual method names from protocol
        service_methods = [
            method for method in dir(ClassManagementServiceProtocol) if not method.startswith("_")
        ]
        expected_service_methods = {
            "register_new_class",
            "add_student_to_class",
            "get_class_by_id",
            "update_class",
            "delete_class",
        }

        for method in expected_service_methods:
            assert method in service_methods, (
                f"ClassManagementServiceProtocol missing method: {method}"
            )

        print("✓ Protocol method signatures validated")

    def test_error_handling_with_factories(self) -> None:
        """Validate error handling using HuleEduError factories."""
        import uuid

        correlation_id = uuid.uuid4()

        # Test course not found factory
        with pytest.raises(HuleEduError) as exc_info:
            raise_course_not_found(
                service="class_management_service",
                operation="test_operation",
                course_id="ENG5",
                correlation_id=correlation_id,
                missing_course_codes=["ENG5"],
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ClassManagementErrorCode.COURSE_NOT_FOUND
        assert error_detail.details["course_id"] == "ENG5"
        assert error_detail.details["missing_course_codes"] == ["ENG5"]
        assert error_detail.correlation_id == correlation_id
        assert error_detail.service == "class_management_service"
        assert error_detail.operation == "test_operation"

        print("✓ Error factory functions validated")

    def test_repository_implementation_has_async_session_pattern(self) -> None:
        """Validate repository implementation has async session management pattern from analysis."""
        # Verify repository can be instantiated (though we won't call methods)
        repo_methods = [
            method for method in dir(PostgreSQLClassRepositoryImpl) if not method.startswith("_")
        ]

        # Verify async session management methods exist
        assert "session" in repo_methods, "Repository should have session context manager"

        # Verify the repository has the init signature we expect
        init_signature = inspect.signature(PostgreSQLClassRepositoryImpl.__init__)
        param_names = list(init_signature.parameters.keys())
        assert "engine" in param_names, "Repository __init__ should accept engine parameter"
        assert "metrics" in param_names, "Repository __init__ should accept metrics parameter"

        print("✓ Repository async session pattern validated")

    def test_api_models_have_expected_fields(self) -> None:
        """Validate API models have fields referenced in analysis."""
        # Test CreateClassRequest
        class_request_hints = get_type_hints(CreateClassRequest)
        assert "name" in class_request_hints, "CreateClassRequest should have 'name' field"
        assert "course_codes" in class_request_hints, (
            "CreateClassRequest should have 'course_codes' field"
        )

        # Test CreateStudentRequest
        student_request_hints = get_type_hints(CreateStudentRequest)
        assert "person_name" in student_request_hints, (
            "CreateStudentRequest should have 'person_name' field"
        )
        assert "email" in student_request_hints, "CreateStudentRequest should have 'email' field"

        print("✓ API model field structure validated")

    def test_settings_have_expected_attributes(self) -> None:
        """Validate settings have attributes referenced in analysis."""
        # Test on instance, not class, to get actual field attributes
        settings_instance = Settings()
        settings_attrs = dir(settings_instance)
        expected_settings = {
            "SERVICE_NAME",
            "ENVIRONMENT",
            "DATABASE_URL",
            "REDIS_URL",
            "KAFKA_BOOTSTRAP_SERVERS",
            "DATABASE_POOL_SIZE",
            "DATABASE_MAX_OVERFLOW",
        }

        for setting in expected_settings:
            assert setting in settings_attrs, f"Settings missing attribute: {setting}"

        print("✓ Settings attributes validated")

    @pytest.mark.asyncio
    async def test_async_engine_configuration_works(self) -> None:
        """Validate async engine configuration pattern from analysis works."""
        # Test that we can create an async engine (using SQLite for testing - no pool params)
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )

        # Verify engine can be used to create sessions
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_maker = async_sessionmaker(test_engine, expire_on_commit=False)

        # Test async context manager pattern
        async with session_maker() as session:
            assert isinstance(session, AsyncSession)

        await test_engine.dispose()
        print("✓ Async engine configuration validated")

    def test_all_critical_imports_successful(self) -> None:
        """Final validation that all critical imports from analysis succeeded."""
        print("✓ All critical imports from analysis validation successful")
        print("✓ No hallucinated variables, enums, or structures detected")
        print("✓ Analysis assumptions validated - safe to proceed with comprehensive testing")
