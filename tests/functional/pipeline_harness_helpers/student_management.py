"""Student and class management helper for pipeline tests."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from tests.utils.auth_manager import AuthTestManager, AuthTestUser
    from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.student_management")

# All student names from essay files (properly capitalized)
TEST_STUDENT_NAMES = [
    "Alva Lemos",
    "Amanda Frantz",
    "Arve Bergström",
    "Axel Karlsson",
    "Cornelia Kardborn",
    "Ebba Noren Bergsröm",
    "Ebba Saviluoto",
    "Edgar Gezelius",
    "Elin Bogren",
    "Ellie Rankin",
    "Elvira Johansson",
    "Emil Pihlman",
    "Emil Zäll Jernberg",
    "Emma Wüst",
    "Erik Arvman",
    "Figg Eriksson",
    "Jagoda Struzik",
    "Jonathan Hedqvist",
    "Leon Gustavsson",
    "Manuel Gren",
    "Melek Özturk",
    "Nelli Moilanen",
    "Sam Höglund Öman",
    "Stella Sellström",
    "Vera Karlberg",
    "Simon Pub",
    "Tindra Cruz",
]


class StudentManagementHelper:
    """Helper class for managing students and classes in tests."""

    @staticmethod
    async def create_class_with_roster(
        service_manager: "ServiceTestManager",
        auth_manager: "AuthTestManager",
        class_name: str = "Book Report ES24B Test Class",
        student_names: Optional[List[str]] = None,
    ) -> Tuple[str, "AuthTestUser", List[str]]:
        """
        Create a test class with all students from essay files.

        Args:
            service_manager: Service manager for API requests
            auth_manager: Auth manager for user creation
            class_name: Name for the test class
            student_names: List of student names to create (defaults to TEST_STUDENT_NAMES)

        Returns:
            Tuple of (class_id, teacher_user, student_ids)
        """
        if student_names is None:
            student_names = TEST_STUDENT_NAMES

        logger.info(f"🏫 Setting up test class with {len(student_names)} students")

        # Create teacher user
        teacher_user = auth_manager.create_test_user(role="teacher")

        # Create the class
        class_data = {
            "name": class_name,
            "course_codes": ["ENG5"],  # Must match CourseCode enum
        }

        try:
            response = await service_manager.make_request(
                "POST",
                "class_management_service",
                "/v1/classes/",
                json=class_data,
                user=teacher_user,
            )
            created_class_id = str(response["id"])
            logger.info(f"✅ Created class with ID: {created_class_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to create test class: {e}")

        # Create all students and associate them with the class
        student_ids = []
        for student_name in student_names:
            parts = student_name.rsplit(" ", 1)
            if len(parts) == 2:
                first_name, last_name = parts
            else:
                first_name = student_name
                last_name = ""

            student_data = {
                "person_name": {"first_name": first_name, "last_name": last_name},
                "email": f"{first_name.lower().replace(' ', '.')}.{last_name.lower()}@test.edu"
                if last_name
                else f"{first_name.lower()}@test.edu",
                "class_ids": [created_class_id],
            }

            try:
                student_response = await service_manager.make_request(
                    "POST",
                    "class_management_service",
                    "/v1/classes/students",
                    json=student_data,
                    user=teacher_user,
                )
                student_id = student_response.get("id")
                if student_id:
                    student_ids.append(str(student_id))
                logger.debug(f"✅ Created student: {student_name}")
            except Exception as e:
                logger.warning(f"Failed to create student {student_name}: {e}")

        logger.info(f"✅ Test class setup complete with {len(student_names)} students")
        return created_class_id, teacher_user, student_ids

    @staticmethod
    async def verify_student_associations(
        service_manager: "ServiceTestManager",
        teacher_user: "AuthTestUser",
        batch_id: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch suggested student associations and confirm them as teacher.

        Args:
            service_manager: Service manager for API requests
            teacher_user: Teacher user to confirm associations
            batch_id: Batch ID to get associations for
            correlation_id: Correlation ID for tracking

        Returns:
            Confirmation response from the API
        """
        # Get suggested associations
        response = await service_manager.make_request(
            method="GET",
            service="class_management_service",
            path=f"/v1/batches/{batch_id}/student-associations",
            user=teacher_user,
            correlation_id=correlation_id,
        )

        associations = response.get("associations", [])
        logger.info(f"📋 Retrieved {len(associations)} suggested associations")

        # Confirm all associations
        confirmation_data = {
            "associations": [
                {
                    "essay_id": assoc["essay_id"],
                    "student_id": assoc["suggested_student_id"],
                    "confirmed": True,
                }
                for assoc in associations
            ],
            "confirmation_method": "manual_teacher_review",
        }

        # Confirm associations
        confirm_response = await service_manager.make_request(
            method="POST",
            service="class_management_service",
            path=f"/v1/batches/{batch_id}/student-associations/confirm",
            json=confirmation_data,
            user=teacher_user,
            correlation_id=correlation_id,
        )

        logger.info("✅ Teacher confirmed all student-essay associations")
        return confirm_response
