"""
Concurrent teacher performance tests for Class Management Service.

Tests realistic educational scenarios with multiple teachers operating simultaneously.
Focus on robust service logic under concurrent educational workloads.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Tuple

import pytest

from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.tests.performance.conftest import (
    EducationalPerformanceMetrics,
    EducationalTestDataGenerator,
    measure_async_operation,
)


@pytest.mark.asyncio
class TestConcurrentTeacherPerformance:
    """Test concurrent teacher operations under realistic educational loads."""

    async def test_light_concurrent_load_3_teachers(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
        teacher_ids: List[str],
        test_data_generator: EducationalTestDataGenerator,
    ) -> None:
        """Test light concurrent load with 3 teachers (baseline concurrent behavior)."""
        print("\n" + "="*60)
        print("LIGHT CONCURRENT LOAD TEST: 3 Teachers")
        print("="*60)
        
        # Arrange - 3 teachers with realistic workloads
        teachers = teacher_ids[:3]
        
        async def teacher_workload(teacher_id: str, teacher_index: int) -> Dict[str, Any]:
            """Simulate realistic teacher workload."""
            results: Dict[str, Any] = {
                "teacher_id": teacher_id,
                "operations": [],
                "success_count": 0,
                "total_time": 0
            }
            
            start_time = time.perf_counter()
            
            # Each teacher creates 2 classes
            class_requests = test_data_generator.generate_class_requests(2)
            
            for i, class_request in enumerate(class_requests):
                duration, result, success = await measure_async_operation(
                    performance_repository.create_class,
                    teacher_id,
                    class_request
                )
                
                performance_metrics.record_operation("concurrent_class_creation", duration, success)
                results["operations"].append(("class_creation", duration, success))
                
                if success:
                    results["success_count"] += 1
                    
                # Realistic pause between operations (teacher thinking/planning time)
                await asyncio.sleep(0.2)
                
                # After first class, add students to it
                if i == 0 and success:
                    student_requests = test_data_generator.generate_student_requests(3)
                    
                    for student_request in student_requests:
                        duration, student_result, student_success = await measure_async_operation(
                            performance_repository.create_student,
                            teacher_id,
                            student_request
                        )
                        
                        performance_metrics.record_operation("concurrent_student_enrollment", duration, student_success)
                        results["operations"].append(("student_enrollment", duration, student_success))
                        
                        if student_success:
                            results["success_count"] += 1
                            
                        # Brief pause between student additions
                        await asyncio.sleep(0.1)
            
            results["total_time"] = time.perf_counter() - start_time
            return results
        
        # Act - Execute concurrent teacher workloads
        teacher_tasks = [
            teacher_workload(teacher_id, i) 
            for i, teacher_id in enumerate(teachers)
        ]
        
        overall_start = time.perf_counter()
        teacher_results = await asyncio.gather(*teacher_tasks)
        overall_duration = time.perf_counter() - overall_start
        
        # Assert - Validate concurrent performance
        print(f"\n📊 LIGHT LOAD RESULTS (3 teachers, {overall_duration:.2f}s total):")
        
        total_operations = 0
        total_successes = 0
        
        for result in teacher_results:
            teacher_ops = len(result["operations"])
            teacher_successes = result["success_count"]
            success_rate = (teacher_successes / teacher_ops * 100) if teacher_ops > 0 else 0
            
            print(f"  👨‍🏫 {result['teacher_id']}: {teacher_successes}/{teacher_ops} ops ({success_rate:.1f}%) in {result['total_time']:.2f}s")
            
            total_operations += teacher_ops
            total_successes += teacher_successes
        
        overall_success_rate = (total_successes / total_operations * 100) if total_operations > 0 else 0
        print(f"  🎯 Overall: {total_successes}/{total_operations} ops ({overall_success_rate:.1f}%)")
        
        # Strict thresholds for light load (should be near-perfect)
        assert overall_success_rate >= 95.0, f"Light load success rate {overall_success_rate:.1f}% below 95% threshold"
        assert overall_duration < 15.0, f"Light load took {overall_duration:.2f}s, expected < 15s"
        
        # Verify data isolation - check that teachers created their own classes
        for result in teacher_results:
            teacher_id = result["teacher_id"]
            classes_created = [op for op in result["operations"] if op[0] == "class_creation" and op[2]]
            assert len(classes_created) >= 1, f"Teacher {teacher_id} should have created at least 1 class"
        
        print("✅ Light concurrent load test passed")

    async def test_normal_concurrent_load_7_teachers(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
        teacher_ids: List[str],
        test_data_generator: EducationalTestDataGenerator,
    ) -> None:
        """Test normal concurrent load with 7 teachers (typical school day operations)."""
        print("\n" + "="*60)
        print("NORMAL CONCURRENT LOAD TEST: 7 Teachers")
        print("="*60)
        
        # Arrange - 7 teachers with varied workloads
        teachers = teacher_ids[:7]
        
        async def mixed_teacher_workload(teacher_id: str, workload_type: str) -> Dict[str, Any]:
            """Simulate different types of teacher workloads."""
            results: Dict[str, Any] = {
                "teacher_id": teacher_id,
                "workload_type": workload_type,
                "operations": [],
                "success_count": 0,
                "total_time": 0
            }
            
            start_time = time.perf_counter()
            
            if workload_type == "class_heavy":
                # Teacher focusing on class creation (3-4 classes)
                class_requests = test_data_generator.generate_class_requests(4)
                
                for class_request in class_requests:
                    duration, result, success = await measure_async_operation(
                        performance_repository.create_class,
                        teacher_id,
                        class_request
                    )
                    
                    performance_metrics.record_operation("concurrent_class_creation", duration, success)
                    results["operations"].append(("class_creation", duration, success))
                    
                    if success:
                        results["success_count"] += 1
                        
                    await asyncio.sleep(0.15)  # Realistic planning time
                    
            elif workload_type == "student_heavy":
                # Teacher focusing on student management (1 class, many students)
                class_request = test_data_generator.generate_class_requests(1)[0]
                
                duration, class_result, class_success = await measure_async_operation(
                    performance_repository.create_class,
                    teacher_id,
                    class_request
                )
                
                performance_metrics.record_operation("concurrent_class_creation", duration, class_success)
                results["operations"].append(("class_creation", duration, class_success))
                
                if class_success:
                    results["success_count"] += 1
                    
                    # Add 8 students to the class
                    student_requests = test_data_generator.generate_student_requests(8)
                    
                    for student_request in student_requests:
                        duration, student_result, student_success = await measure_async_operation(
                            performance_repository.create_student,
                            teacher_id,
                            student_request
                        )
                        
                        performance_metrics.record_operation("concurrent_student_enrollment", duration, student_success)
                        results["operations"].append(("student_enrollment", duration, student_success))
                        
                        if student_success:
                            results["success_count"] += 1
                            
                        await asyncio.sleep(0.05)  # Quick student additions
                        
            else:  # balanced workload
                # Mixed operations
                class_requests = test_data_generator.generate_class_requests(2)
                
                for class_request in class_requests:
                    duration, result, success = await measure_async_operation(
                        performance_repository.create_class,
                        teacher_id,
                        class_request
                    )
                    
                    performance_metrics.record_operation("concurrent_class_creation", duration, success)
                    results["operations"].append(("class_creation", duration, success))
                    
                    if success:
                        results["success_count"] += 1
                        
                        # Add 3 students per class
                        student_requests = test_data_generator.generate_student_requests(3)
                        
                        for student_request in student_requests:
                            duration, student_result, student_success = await measure_async_operation(
                                performance_repository.create_student,
                                teacher_id,
                                student_request
                            )
                            
                            performance_metrics.record_operation("concurrent_student_enrollment", duration, student_success)
                            results["operations"].append(("student_enrollment", duration, student_success))
                            
                            if student_success:
                                results["success_count"] += 1
                                
                            await asyncio.sleep(0.08)
                    
                    await asyncio.sleep(0.2)
            
            results["total_time"] = time.perf_counter() - start_time
            return results
        
        # Assign different workload types to teachers
        workload_types = ["class_heavy", "student_heavy", "balanced", "balanced", "class_heavy", "student_heavy", "balanced"]
        
        teacher_tasks = [
            mixed_teacher_workload(teacher_id, workload_type)
            for teacher_id, workload_type in zip(teachers, workload_types)
        ]
        
        # Act - Execute concurrent mixed workloads
        overall_start = time.perf_counter()
        teacher_results = await asyncio.gather(*teacher_tasks)
        overall_duration = time.perf_counter() - overall_start
        
        # Assert - Validate normal load performance
        print(f"\n📊 NORMAL LOAD RESULTS (7 teachers, {overall_duration:.2f}s total):")
        
        total_operations = 0
        total_successes = 0
        workload_stats = {}
        
        for result in teacher_results:
            teacher_ops = len(result["operations"])
            teacher_successes = result["success_count"]
            success_rate = (teacher_successes / teacher_ops * 100) if teacher_ops > 0 else 0
            workload = result["workload_type"]
            
            print(f"  👨‍🏫 {result['teacher_id']} ({workload}): {teacher_successes}/{teacher_ops} ops ({success_rate:.1f}%) in {result['total_time']:.2f}s")
            
            total_operations += teacher_ops
            total_successes += teacher_successes
            
            if workload not in workload_stats:
                workload_stats[workload] = {"ops": 0, "successes": 0}
            workload_stats[workload]["ops"] += teacher_ops
            workload_stats[workload]["successes"] += teacher_successes
        
        overall_success_rate = (total_successes / total_operations * 100) if total_operations > 0 else 0
        print(f"  🎯 Overall: {total_successes}/{total_operations} ops ({overall_success_rate:.1f}%)")
        
        # Show workload type performance
        for workload, stats in workload_stats.items():
            workload_rate = (stats["successes"] / stats["ops"] * 100) if stats["ops"] > 0 else 0
            print(f"  📋 {workload}: {stats['successes']}/{stats['ops']} ops ({workload_rate:.1f}%)")
        
        # Thresholds for normal load (realistic expectations)
        assert overall_success_rate >= 92.0, f"Normal load success rate {overall_success_rate:.1f}% below 92% threshold"
        assert overall_duration < 25.0, f"Normal load took {overall_duration:.2f}s, expected < 25s"
        
        # Verify reasonable performance per workload type
        for workload, stats in workload_stats.items():
            workload_rate = (stats["successes"] / stats["ops"] * 100) if stats["ops"] > 0 else 0
            assert workload_rate >= 90.0, f"{workload} workload success rate {workload_rate:.1f}% below 90%"
        
        print("✅ Normal concurrent load test passed")

    async def test_peak_registration_load_12_teachers(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
        teacher_ids: List[str],
        test_data_generator: EducationalTestDataGenerator,
    ) -> None:
        """Test peak registration load with 12 teachers (start-of-semester scenario)."""
        print("\n" + "="*60)
        print("PEAK REGISTRATION LOAD TEST: 12 Teachers")
        print("="*60)
        
        # Arrange - 12 teachers simulating registration period
        teachers = teacher_ids[:12]
        
        async def registration_workload(teacher_id: str, teacher_index: int) -> Dict[str, Any]:
            """Simulate intense registration period workload."""
            results: Dict[str, Any] = {
                "teacher_id": teacher_id,
                "operations": [],
                "success_count": 0,
                "total_time": 0
            }
            
            start_time = time.perf_counter()
            
            # During registration, teachers create multiple classes rapidly
            class_count = 3 if teacher_index % 2 == 0 else 4  # Varied workload
            class_requests = test_data_generator.generate_class_requests(class_count)
            
            for class_request in class_requests:
                duration, result, success = await measure_async_operation(
                    performance_repository.create_class,
                    teacher_id,
                    class_request
                )
                
                performance_metrics.record_operation("peak_class_creation", duration, success)
                results["operations"].append(("class_creation", duration, success))
                
                if success:
                    results["success_count"] += 1
                    
                # Minimal delay during registration rush
                await asyncio.sleep(0.1)
            
            results["total_time"] = time.perf_counter() - start_time
            return results
        
        # Act - Simulate registration rush
        teacher_tasks = [
            registration_workload(teacher_id, i)
            for i, teacher_id in enumerate(teachers)
        ]
        
        overall_start = time.perf_counter()
        teacher_results = await asyncio.gather(*teacher_tasks)
        overall_duration = time.perf_counter() - overall_start
        
        # Assert - Validate peak load performance
        print(f"\n📊 PEAK REGISTRATION RESULTS (12 teachers, {overall_duration:.2f}s total):")
        
        total_operations = 0
        total_successes = 0
        response_times = []
        
        for result in teacher_results:
            teacher_ops = len(result["operations"])
            teacher_successes = result["success_count"]
            success_rate = (teacher_successes / teacher_ops * 100) if teacher_ops > 0 else 0
            
            teacher_response_times = [op[1] for op in result["operations"]]
            avg_response_time = sum(teacher_response_times) / len(teacher_response_times) if teacher_response_times else 0
            response_times.extend(teacher_response_times)
            
            print(f"  👨‍🏫 {result['teacher_id']}: {teacher_successes}/{teacher_ops} ops ({success_rate:.1f}%, avg: {avg_response_time:.3f}s)")
            
            total_operations += teacher_ops
            total_successes += teacher_successes
        
        overall_success_rate = (total_successes / total_operations * 100) if total_operations > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        
        print(f"  🎯 Overall: {total_successes}/{total_operations} ops ({overall_success_rate:.1f}%)")
        print(f"  ⏱️  Response times: avg={avg_response_time:.3f}s, max={max_response_time:.3f}s")
        
        # Peak load thresholds (more lenient but still robust)
        assert overall_success_rate >= 88.0, f"Peak load success rate {overall_success_rate:.1f}% below 88% threshold"
        assert overall_duration < 20.0, f"Peak load took {overall_duration:.2f}s, expected < 20s"
        assert avg_response_time < 0.100, f"Average response time {avg_response_time:.3f}s too high under peak load"
        assert max_response_time < 0.500, f"Max response time {max_response_time:.3f}s too high under peak load"
        
        # Verify that most teachers completed their workload successfully
        successful_teachers = sum(1 for result in teacher_results if result["success_count"] > 0)
        assert successful_teachers >= 10, f"Only {successful_teachers}/12 teachers completed operations successfully"
        
        print("✅ Peak registration load test passed")

    async def test_concurrent_data_isolation(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
        teacher_ids: List[str],
        test_data_generator: EducationalTestDataGenerator,
    ) -> None:
        """Test that concurrent teachers don't interfere with each other's data."""
        print("\n" + "="*60)
        print("CONCURRENT DATA ISOLATION TEST: 5 Teachers")
        print("="*60)
        
        # Arrange - 5 teachers with predictable data patterns
        teachers = teacher_ids[:5]
        
        async def isolated_teacher_workload(teacher_id: str, teacher_index: int) -> Dict[str, Any]:
            """Create predictable data to verify isolation."""
            results: Dict[str, Any] = {
                "teacher_id": teacher_id,
                "classes_created": [],
                "students_created": [],
                "operations": [],
                "success_count": 0
            }
            
            # Create 2 classes with predictable names
            for class_idx in range(2):
                class_request = CreateClassRequest(
                    name=f"IsolationTest_{teacher_index}_{class_idx}",
                    course_codes=[CourseCode.ENG5]
                )
                
                duration, result, success = await measure_async_operation(
                    performance_repository.create_class,
                    teacher_id,
                    class_request
                )
                
                results["operations"].append(("class_creation", duration, success))
                
                if success:
                    results["success_count"] += 1
                    results["classes_created"].append(result.name)
                    
                    # Add 2 students to each class
                    for student_idx in range(2):
                        student_request = CreateStudentRequest(
                            person_name=PersonNameV1(
                                first_name=f"Student{teacher_index}_{class_idx}_{student_idx}",
                                last_name=f"Teacher{teacher_index}"
                            ),
                            email=f"student.{teacher_index}.{class_idx}.{student_idx}@isolation.edu"
                        )
                        
                        duration, student_result, student_success = await measure_async_operation(
                            performance_repository.create_student,
                            teacher_id,
                            student_request
                        )
                        
                        results["operations"].append(("student_creation", duration, student_success))
                        
                        if student_success:
                            results["success_count"] += 1
                            results["students_created"].append(student_result.email)
                
                await asyncio.sleep(0.1)
            
            return results
        
        # Act - Execute concurrent isolated workloads
        teacher_tasks = [
            isolated_teacher_workload(teacher_id, i)
            for i, teacher_id in enumerate(teachers)
        ]
        
        teacher_results = await asyncio.gather(*teacher_tasks)
        
        # Assert - Verify data isolation
        print(f"\n📊 DATA ISOLATION RESULTS:")
        
        all_class_names: List[str] = []
        all_student_emails: List[str] = []
        
        for i, result in enumerate(teacher_results):
            teacher_classes = len(result["classes_created"])
            teacher_students = len(result["students_created"])
            
            print(f"  👨‍🏫 Teacher {i}: {teacher_classes} classes, {teacher_students} students")
            print(f"    Classes: {result['classes_created']}")
            print(f"    Students: {result['students_created'][:3]}...")  # Show first 3
            
            all_class_names.extend(result["classes_created"])
            all_student_emails.extend(result["students_created"])
            
            # Verify teacher created expected data
            assert teacher_classes >= 1, f"Teacher {i} should have created at least 1 class"
            assert teacher_students >= 1, f"Teacher {i} should have created at least 1 student"
            
            # Verify naming patterns match teacher index
            for class_name in result["classes_created"]:
                assert f"IsolationTest_{i}_" in class_name, f"Class name {class_name} doesn't match teacher {i}"
            
            for email in result["students_created"]:
                assert f"student.{i}." in email, f"Student email {email} doesn't match teacher {i}"
        
        # Verify no duplicate data
        assert len(all_class_names) == len(set(all_class_names)), "Duplicate class names found - data isolation failed"
        assert len(all_student_emails) == len(set(all_student_emails)), "Duplicate student emails found - data isolation failed"
        
        # Verify cross-contamination didn't occur
        for i, result in enumerate(teacher_results):
            for other_result in teacher_results:
                if other_result["teacher_id"] != result["teacher_id"]:
                    # Check no classes from other teachers
                    for class_name in other_result["classes_created"]:
                        assert class_name not in result["classes_created"], f"Teacher {i} has class from another teacher"
                    
                    # Check no students from other teachers
                    for email in other_result["students_created"]:
                        assert email not in result["students_created"], f"Teacher {i} has student from another teacher"
        
        print("✅ Concurrent data isolation test passed")

    async def test_concurrent_performance_summary(
        self,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Print comprehensive concurrent performance summary."""
        print("\n" + "="*80)
        print("CONCURRENT TEACHER PERFORMANCE SUMMARY")
        print("="*80)
        
        stats = performance_metrics.get_educational_statistics()
        
        concurrent_operations = [
            "concurrent_class_creation",
            "concurrent_student_enrollment", 
            "peak_class_creation"
        ]
        
        for operation_type in concurrent_operations:
            operation_stats = stats.get(operation_type, {})
            
            if operation_stats.get("total_operations", 0) > 0:
                print(f"\n{operation_type.upper().replace('_', ' ')}:")
                print(f"  Total operations: {operation_stats['total_operations']}")
                print(f"  Success rate: {operation_stats['success_rate']:.1f}%")
                print(f"  Response times:")
                print(f"    Mean: {operation_stats['response_times']['mean']:.3f}s")
                print(f"    Median: {operation_stats['response_times']['median']:.3f}s")
                print(f"    P95: {operation_stats['response_times']['p95']:.3f}s")
                print(f"    P99: {operation_stats['response_times']['p99']:.3f}s")
                print(f"    Max: {operation_stats['response_times']['max']:.3f}s")
        
        print("\n" + "="*80)
        
        # Overall concurrent performance validation
        concurrent_class_stats = stats.get("concurrent_class_creation", {})
        if concurrent_class_stats.get("total_operations", 0) > 0:
            assert concurrent_class_stats["success_rate"] >= 90.0, "Concurrent class creation success rate too low"
            assert concurrent_class_stats["response_times"]["mean"] < 0.100, "Concurrent class creation mean time too high"
        
        concurrent_student_stats = stats.get("concurrent_student_enrollment", {})
        if concurrent_student_stats.get("total_operations", 0) > 0:
            assert concurrent_student_stats["success_rate"] >= 90.0, "Concurrent student enrollment success rate too low"
            assert concurrent_student_stats["response_times"]["mean"] < 0.080, "Concurrent student enrollment mean time too high"
        
        print("✅ All concurrent teacher performance tests completed successfully")