"""
Performance test fixtures for Class Management Service.

Provides comprehensive fixtures for educational workflow performance testing
following successful patterns from LLM Provider Service.
"""

from __future__ import annotations

import asyncio
import statistics
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Tuple
from unittest.mock import Mock

import pytest
from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.models_db import Base, Student, UserClass


class EducationalPerformanceMetrics:
    """Comprehensive performance metrics for educational workflows."""

    def __init__(self) -> None:
        self.operation_times: Dict[str, List[float]] = {}
        self.success_counts: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}
        self.database_connection_times: List[float] = []
        self.event_publishing_times: List[float] = []

    def record_operation(self, operation_type: str, duration: float, success: bool) -> None:
        """Record performance metrics for a specific operation."""
        if operation_type not in self.operation_times:
            self.operation_times[operation_type] = []
            self.success_counts[operation_type] = 0
            self.error_counts[operation_type] = 0

        self.operation_times[operation_type].append(duration)
        if success:
            self.success_counts[operation_type] += 1
        else:
            self.error_counts[operation_type] += 1

    def record_database_connection(self, duration: float) -> None:
        """Record database connection time."""
        self.database_connection_times.append(duration)

    def record_event_publishing(self, duration: float) -> None:
        """Record event publishing time."""
        self.event_publishing_times.append(duration)

    def get_operation_stats(self, operation_type: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a specific operation type."""
        if operation_type not in self.operation_times:
            return {"error": "Operation type not found"}

        times = self.operation_times[operation_type]
        total_ops = len(times)
        success_count = self.success_counts.get(operation_type, 0)
        error_count = self.error_counts.get(operation_type, 0)

        return {
            "total_operations": total_ops,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": (success_count / total_ops * 100) if total_ops > 0 else 0,
            "response_times": {
                "min": min(times) if times else 0,
                "max": max(times) if times else 0,
                "mean": statistics.mean(times) if times else 0,
                "median": statistics.median(times) if times else 0,
                "p95": self.get_percentile(times, 95) if times else 0,
                "p99": self.get_percentile(times, 99) if times else 0,
            },
        }

    def get_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile for response times."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((percentile / 100) * len(sorted_values))
        if index >= len(sorted_values):
            index = len(sorted_values) - 1
        return sorted_values[index]

    def get_educational_statistics(self) -> Dict[str, Any]:
        """Get comprehensive educational workflow statistics."""
        return {
            "class_creation": self.get_operation_stats("class_creation"),
            "student_enrollment": self.get_operation_stats("student_enrollment"),
            "student_update": self.get_operation_stats("student_update"),
            "bulk_operations": self.get_operation_stats("bulk_operations"),
            "database_performance": {
                "connection_times": {
                    "mean": statistics.mean(self.database_connection_times)
                    if self.database_connection_times
                    else 0,
                    "p95": self.get_percentile(self.database_connection_times, 95),
                }
            },
            "event_publishing": {
                "times": {
                    "mean": statistics.mean(self.event_publishing_times)
                    if self.event_publishing_times
                    else 0,
                    "p95": self.get_percentile(self.event_publishing_times, 95),
                }
            },
        }

    def print_performance_summary(self) -> None:
        """Print comprehensive performance summary for educational workflows."""
        stats = self.get_educational_statistics()

        print("\n" + "=" * 80)
        print("EDUCATIONAL WORKFLOW PERFORMANCE SUMMARY")
        print("=" * 80)

        for operation_type, operation_stats in stats.items():
            if operation_type in ["database_performance", "event_publishing"]:
                continue

            print(f"\n{operation_type.upper()} PERFORMANCE:")
            print(f"  Total operations: {operation_stats['total_operations']}")
            print(f"  Success rate: {operation_stats['success_rate']:.1f}%")
            print("  Response times:")
            print(f"    Mean: {operation_stats['response_times']['mean']:.4f}s")
            print(f"    Median: {operation_stats['response_times']['median']:.4f}s")
            print(f"    P95: {operation_stats['response_times']['p95']:.4f}s")
            print(f"    P99: {operation_stats['response_times']['p99']:.4f}s")
            print(f"    Min: {operation_stats['response_times']['min']:.4f}s")
            print(f"    Max: {operation_stats['response_times']['max']:.4f}s")

        print("\nDATABASE PERFORMANCE:")
        db_stats = stats["database_performance"]
        print(f"  Connection time mean: {db_stats['connection_times']['mean']:.4f}s")
        print(f"  Connection time P95: {db_stats['connection_times']['p95']:.4f}s")

        print("\nEVENT PUBLISHING PERFORMANCE:")
        event_stats = stats["event_publishing"]
        print(f"  Publishing time mean: {event_stats['times']['mean']:.4f}s")
        print(f"  Publishing time P95: {event_stats['times']['p95']:.4f}s")

        print("=" * 80)


class EducationalTestDataGenerator:
    """Generate realistic educational test data for performance testing."""

    @staticmethod
    def generate_teacher_ids(count: int) -> List[str]:
        """Generate realistic teacher IDs for educational institution."""
        # Realistic teacher ID patterns from actual schools
        teacher_prefixes = ["t", "teacher", "staff"]
        return [
            f"{teacher_prefixes[i % len(teacher_prefixes)]}.{i:04d}@school.edu"
            for i in range(1, count + 1)
        ]

    @staticmethod
    def generate_class_requests(count: int) -> List[CreateClassRequest]:
        """Generate realistic class creation requests for school environment."""
        # Realistic course distribution (English/Math more common)
        course_weights = {
            CourseCode.ENG5: 3,
            CourseCode.ENG6: 3,
            CourseCode.ENG7: 2,
            CourseCode.SV1: 3,
            CourseCode.SV2: 3,
            CourseCode.SV3: 2,
        }

        # Realistic class naming patterns
        periods = ["Period 1", "Period 2", "Period 3", "Period 4", "Period 5", "Block A", "Block B"]
        room_numbers = ["Room 101", "Room 205", "Room 314", "Lab A", "Library"]
        class_types = ["", "Honors", "Advanced", "Remedial"]

        class_requests = []
        course_list = []

        # Build weighted course list
        for course, weight in course_weights.items():
            course_list.extend([course] * weight)

        for i in range(count):
            course = course_list[i % len(course_list)]
            period = periods[i % len(periods)]
            room = room_numbers[i % len(room_numbers)]
            class_type = class_types[i % len(class_types)]

            # Build realistic class name
            base_name = f"{course.value.replace('_', ' ')}"
            if class_type:
                base_name = f"{base_name} {class_type}"

            class_name = f"{base_name} - {period} ({room})"

            class_requests.append(CreateClassRequest(name=class_name, course_codes=[course]))

        return class_requests

    @staticmethod
    def generate_student_requests(count: int) -> List[CreateStudentRequest]:
        """Generate realistic student creation requests with authentic patterns."""
        # Realistic first names (mix of common names)
        first_names = [
            "Emma",
            "Liam",
            "Olivia",
            "Noah",
            "Ava",
            "Oliver",
            "Sophia",
            "William",
            "Isabella",
            "Elijah",
            "Charlotte",
            "James",
            "Amelia",
            "Benjamin",
            "Mia",
            "Lucas",
            "Harper",
            "Mason",
            "Evelyn",
            "Ethan",
            "Abigail",
            "Alexander",
            "Emily",
            "Henry",
            "Elizabeth",
            "Jacob",
            "Sofia",
            "Michael",
            "Madison",
            "Daniel",
            "Scarlett",
            "Logan",
            "Victoria",
            "Jackson",
            "Aria",
            "Sebastian",
            "Grace",
            "Jack",
            "Chloe",
            "Owen",
            "Camila",
            "Samuel",
            "Penelope",
            "Matthew",
            "Riley",
            "Leo",
            "Layla",
            "John",
            "Lillian",
            "Anthony",
            "Nora",
            "Isaiah",
        ]

        # Realistic last names
        last_names = [
            "Smith",
            "Johnson",
            "Williams",
            "Brown",
            "Jones",
            "Garcia",
            "Miller",
            "Davis",
            "Rodriguez",
            "Martinez",
            "Hernandez",
            "Lopez",
            "Gonzalez",
            "Wilson",
            "Anderson",
            "Thomas",
            "Taylor",
            "Moore",
            "Jackson",
            "Martin",
            "Lee",
            "Perez",
            "Thompson",
            "White",
            "Harris",
            "Sanchez",
            "Clark",
            "Ramirez",
            "Lewis",
            "Robinson",
            "Walker",
            "Young",
            "Allen",
            "King",
            "Wright",
            "Scott",
            "Torres",
            "Nguyen",
            "Hill",
            "Flores",
            "Green",
            "Adams",
            "Nelson",
            "Baker",
            "Hall",
            "Rivera",
            "Campbell",
            "Mitchell",
            "Carter",
            "Roberts",
            "Gomez",
            "Phillips",
            "Evans",
            "Turner",
        ]

        student_requests = []

        for i in range(count):
            first_name = first_names[i % len(first_names)]
            last_name = last_names[(i * 7) % len(last_names)]  # Different cycling pattern

            # Use UUID suffix to ensure global uniqueness across concurrent operations
            unique_suffix = str(uuid.uuid4()).replace("-", "")[:8]

            # Realistic email patterns with guaranteed uniqueness
            email_patterns = [
                f"{first_name.lower()}.{last_name.lower()}.{unique_suffix}@student.school.edu",
                f"{first_name.lower()}{last_name.lower()}.{unique_suffix}@students.edu",
                f"student.{unique_suffix}@student.district.edu",
            ]

            email = email_patterns[i % len(email_patterns)]

            student_requests.append(
                CreateStudentRequest(
                    person_name=PersonNameV1(first_name=first_name, last_name=last_name),
                    email=email,
                )
            )

        return student_requests

    @staticmethod
    def generate_bulk_student_data(
        class_count: int, students_per_class: int | None = None
    ) -> Dict[str, List[CreateStudentRequest]]:
        """Generate bulk student data for multiple classes with realistic class sizes."""
        bulk_data = {}

        # Realistic class size distribution if not specified
        if students_per_class is None:
            # Typical educational class sizes with some variation
            class_size_patterns = [22, 25, 28, 24, 26, 30, 23, 27, 29, 21]
        else:
            class_size_patterns = [students_per_class]

        # Generate enough students for all classes
        total_students_needed = sum(
            class_size_patterns[:class_count] * (class_count // len(class_size_patterns) + 1)
        )
        all_students = EducationalTestDataGenerator.generate_student_requests(total_students_needed)

        student_index = 0
        for class_idx in range(class_count):
            class_key = f"realistic_class_{class_idx + 1}"
            class_size = class_size_patterns[class_idx % len(class_size_patterns)]

            bulk_data[class_key] = all_students[student_index : student_index + class_size]
            student_index += class_size

        return bulk_data


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Provide PostgreSQL testcontainer for performance testing."""
    with PostgresContainer("postgres:15", driver="psycopg2") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> RedisContainer:
    """Provide Redis testcontainer for performance testing."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="function")
async def performance_async_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create async engine with performance-optimized settings."""
    # Get connection URL and convert to asyncpg
    conn_url = postgres_container.get_connection_url()
    if "+psycopg2://" in conn_url:
        conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")

    # Realistic educational application settings
    engine = create_async_engine(
        conn_url,
        echo=False,
        pool_size=25,  # Realistic for 50-100 concurrent teachers
        max_overflow=50,  # Handle registration period spikes
        pool_pre_ping=True,  # Validate connections after idle periods
        pool_recycle=3600,  # Recycle connections hourly (educational apps run long)
        connect_args={
            "command_timeout": 30,  # Reasonable timeout for bulk operations
            "server_settings": {
                "statement_timeout": "45000",  # 45 second timeout for complex queries
                "application_name": "class_management_performance_test",
            },
        },
    )

    # Create database schema and seed courses
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Seed courses (essential for performance tests)
        await conn.execute(
            text("""
            INSERT INTO courses (id, course_code, name, language, skill_level) VALUES
            (gen_random_uuid(), 'ENG5', 'English 5', 'en', 5),
            (gen_random_uuid(), 'ENG6', 'English 6', 'en', 6),
            (gen_random_uuid(), 'ENG7', 'English 7', 'en', 7),
            (gen_random_uuid(), 'SV1', 'Svenska 1', 'sv', 1),
            (gen_random_uuid(), 'SV2', 'Svenska 2', 'sv', 2),
            (gen_random_uuid(), 'SV3', 'Svenska 3', 'sv', 3)
            ON CONFLICT (course_code) DO NOTHING
        """)
        )

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def performance_repository(performance_async_engine: AsyncEngine) -> PostgreSQLClassRepositoryImpl:
    """Create repository with performance-optimized database engine."""
    # Mock metrics to avoid Prometheus overhead in performance tests
    mock_metrics = Mock()
    mock_metrics.record_operation_duration = Mock()
    mock_metrics.record_database_connection = Mock()
    mock_metrics.record_error = Mock()

    return PostgreSQLClassRepositoryImpl[UserClass, Student](performance_async_engine, mock_metrics)


@pytest.fixture
def performance_metrics() -> EducationalPerformanceMetrics:
    """Provide performance metrics collector."""
    return EducationalPerformanceMetrics()


@pytest.fixture
def test_data_generator() -> EducationalTestDataGenerator:
    """Provide test data generator for educational scenarios."""
    return EducationalTestDataGenerator()


@pytest.fixture
def teacher_ids() -> List[str]:
    """Provide realistic teacher IDs for performance testing (small school: ~50 teachers)."""
    return EducationalTestDataGenerator.generate_teacher_ids(50)


async def measure_async_operation(
    operation_func: Any, *args: Any, **kwargs: Any
) -> Tuple[float, Any, bool]:
    """Measure the performance of an async operation."""
    start_time = time.perf_counter()
    success = True
    result = None

    try:
        result = await operation_func(*args, **kwargs)
    except Exception as e:
        success = False
        result = e  # Return the actual exception for debugging

    duration = time.perf_counter() - start_time
    return duration, result, success


def measure_sync_operation(
    operation_func: Any, *args: Any, **kwargs: Any
) -> Tuple[float, Any, bool]:
    """Measure the performance of a sync operation."""
    start_time = time.perf_counter()
    success = True
    result = None

    try:
        result = operation_func(*args, **kwargs)
    except Exception as e:
        success = False
        result = e  # Return the actual exception for debugging

    duration = time.perf_counter() - start_time
    return duration, result, success


@pytest.fixture
def async_performance_measurer() -> Any:
    """Provide async operation performance measurement utility."""
    return measure_async_operation


@pytest.fixture
def sync_performance_measurer() -> Any:
    """Provide sync operation performance measurement utility."""
    return measure_sync_operation


# Performance test execution helpers
async def execute_concurrent_operations(
    operation_func: Any, operation_args_list: List[tuple], max_concurrent: int = 10
) -> List[Tuple[float, Any, bool]]:
    """Execute operations concurrently with controlled concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def controlled_operation(args: tuple) -> Tuple[float, Any, bool]:
        async with semaphore:
            return await measure_async_operation(operation_func, *args)

    tasks = [controlled_operation(args) for args in operation_args_list]
    return await asyncio.gather(*tasks)


@pytest.fixture
def concurrent_executor() -> Any:
    """Provide concurrent operation executor."""
    return execute_concurrent_operations


# Educational workflow simulation helpers
class EducationalWorkflowSimulator:
    """Simulate realistic educational workflows for performance testing."""

    def __init__(
        self, repository: PostgreSQLClassRepositoryImpl, metrics: EducationalPerformanceMetrics
    ):
        self.repository = repository
        self.metrics = metrics

    async def simulate_class_creation_workflow(
        self, teacher_id: str, class_request: CreateClassRequest
    ) -> bool:
        """Simulate complete class creation workflow."""
        duration, _, success = await measure_async_operation(
            self.repository.create_class, teacher_id, class_request
        )

        self.metrics.record_operation("class_creation", duration, success)
        return success

    async def simulate_student_enrollment_workflow(
        self, teacher_id: str, student_request: CreateStudentRequest
    ) -> bool:
        """Simulate complete student enrollment workflow."""
        duration, _, success = await measure_async_operation(
            self.repository.create_student, teacher_id, student_request
        )

        self.metrics.record_operation("student_enrollment", duration, success)
        return success

    async def simulate_bulk_student_import(
        self, teacher_id: str, student_requests: List[CreateStudentRequest]
    ) -> List[bool]:
        """Simulate bulk student import workflow."""
        results = []

        for student_request in student_requests:
            duration, _, success = await measure_async_operation(
                self.repository.create_student, teacher_id, student_request
            )

            self.metrics.record_operation("bulk_operations", duration, success)
            results.append(success)

        return results


@pytest.fixture
def educational_workflow_simulator(
    performance_repository: PostgreSQLClassRepositoryImpl,
    performance_metrics: EducationalPerformanceMetrics,
) -> EducationalWorkflowSimulator:
    """Provide educational workflow simulator for performance testing."""
    return EducationalWorkflowSimulator(performance_repository, performance_metrics)
