#!/usr/bin/env python3
"""
Distributed test runner for Essay Lifecycle Service.

Orchestrates comprehensive distributed testing scenarios including:
- Docker Compose infrastructure setup
- Multi-instance coordination testing
- Performance and load validation
- Race condition prevention verification
- Redis state consistency testing

Usage:
    python run_distributed_tests.py [--scenario SCENARIO] [--instances COUNT] [--duration SECONDS]

Scenarios:
    all: Run complete test suite (default)
    race_conditions: Test concurrent race condition prevention
    redis_consistency: Test Redis state consistency under load
    performance: Test performance and scaling
    docker_compose: Test full Docker Compose infrastructure

Examples:
    python run_distributed_tests.py --scenario all
    python run_distributed_tests.py --scenario race_conditions --instances 5
    python run_distributed_tests.py --scenario performance --duration 120
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("distributed_test_results.log"),
    ]
)
logger = logging.getLogger("distributed_test_runner")


class DistributedTestRunner:
    """Orchestrates distributed testing scenarios."""

    def __init__(self, instances: int = 3, duration: int = 60) -> None:
        self.instances = instances
        self.duration = duration
        self.test_results: Dict[str, Any] = {}
        self.start_time = time.time()

    async def run_scenario(self, scenario: str) -> Dict[str, Any]:
        """Run specified test scenario."""
        
        logger.info(f"🚀 Starting distributed test scenario: {scenario}")
        logger.info(f"   - Instances: {self.instances}")
        logger.info(f"   - Duration: {self.duration}s")
        
        scenario_start = time.time()
        
        try:
            if scenario == "all":
                return await self._run_all_scenarios()
            elif scenario == "race_conditions":
                return await self._run_race_condition_tests()
            elif scenario == "redis_consistency":
                return await self._run_redis_consistency_tests()
            elif scenario == "performance":
                return await self._run_performance_tests()
            elif scenario == "docker_compose":
                return await self._run_docker_compose_tests()
            else:
                raise ValueError(f"Unknown scenario: {scenario}")
                
        except Exception as e:
            logger.error(f"❌ Scenario {scenario} failed: {e}")
            return {
                "scenario": scenario,
                "success": False,
                "error": str(e),
                "duration": time.time() - scenario_start,
            }

    async def _run_all_scenarios(self) -> Dict[str, Any]:
        """Run complete test suite."""
        
        scenarios = ["race_conditions", "redis_consistency", "performance"]
        results = {}
        
        for scenario in scenarios:
            logger.info(f"📋 Running scenario: {scenario}")
            result = await self.run_scenario(scenario)
            results[scenario] = result
            
            if not result.get("success", False):
                logger.warning(f"⚠️  Scenario {scenario} failed, continuing with others...")
            
            # Brief pause between scenarios
            await asyncio.sleep(2)
        
        # Calculate overall results
        total_tests = sum(r.get("tests_run", 0) for r in results.values())
        total_passed = sum(r.get("tests_passed", 0) for r in results.values())
        overall_success = all(r.get("success", False) for r in results.values())
        
        return {
            "scenario": "all",
            "success": overall_success,
            "total_tests": total_tests,
            "total_passed": total_passed,
            "success_rate": total_passed / total_tests if total_tests > 0 else 0,
            "scenario_results": results,
            "duration": time.time() - self.start_time,
        }

    async def _run_race_condition_tests(self) -> Dict[str, Any]:
        """Run race condition prevention tests."""
        
        logger.info("🔄 Testing concurrent race condition prevention...")
        
        # Run pytest with specific test markers
        cmd = [
            "pdm", "run", "pytest", 
            "services/essay_lifecycle_service/tests/distributed/test_concurrent_slot_assignment.py",
            "-v", "-s", "--tb=short",
            f"--junitxml=race_condition_results.xml",
            "-m", "not performance",  # Skip performance-heavy tests for this scenario
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Parse results
            tests_run = result.stdout.count("PASSED") + result.stdout.count("FAILED")
            tests_passed = result.stdout.count("PASSED")
            
            success = result.returncode == 0
            
            if success:
                logger.info(f"✅ Race condition tests passed: {tests_passed}/{tests_run}")
            else:
                logger.error(f"❌ Race condition tests failed: {tests_passed}/{tests_run}")
                logger.error(f"Error output: {result.stderr}")
            
            return {
                "scenario": "race_conditions",
                "success": success,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Race condition tests timed out")
            return {
                "scenario": "race_conditions",
                "success": False,
                "error": "Timeout after 300 seconds",
                "tests_run": 0,
                "tests_passed": 0,
            }

    async def _run_redis_consistency_tests(self) -> Dict[str, Any]:
        """Run Redis state consistency tests."""
        
        logger.info("📊 Testing Redis state consistency under load...")
        
        cmd = [
            "pdm", "run", "pytest",
            "services/essay_lifecycle_service/tests/distributed/test_redis_state_consistency.py", 
            "-v", "-s", "--tb=short",
            f"--junitxml=redis_consistency_results.xml",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            tests_run = result.stdout.count("PASSED") + result.stdout.count("FAILED")
            tests_passed = result.stdout.count("PASSED")
            success = result.returncode == 0
            
            if success:
                logger.info(f"✅ Redis consistency tests passed: {tests_passed}/{tests_run}")
            else:
                logger.error(f"❌ Redis consistency tests failed: {tests_passed}/{tests_run}")
                logger.error(f"Error output: {result.stderr}")
            
            return {
                "scenario": "redis_consistency",
                "success": success,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Redis consistency tests timed out")
            return {
                "scenario": "redis_consistency", 
                "success": False,
                "error": "Timeout after 600 seconds",
                "tests_run": 0,
                "tests_passed": 0,
            }

    async def _run_performance_tests(self) -> Dict[str, Any]:
        """Run performance and scaling tests."""
        
        logger.info("⚡ Testing performance and horizontal scaling...")
        
        cmd = [
            "pdm", "run", "pytest",
            "services/essay_lifecycle_service/tests/distributed/test_distributed_performance.py",
            "-v", "-s", "--tb=short", 
            f"--junitxml=performance_results.xml",
            "-m", "performance",  # Only run performance-marked tests
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            
            tests_run = result.stdout.count("PASSED") + result.stdout.count("FAILED")
            tests_passed = result.stdout.count("PASSED")
            success = result.returncode == 0
            
            if success:
                logger.info(f"✅ Performance tests passed: {tests_passed}/{tests_run}")
            else:
                logger.error(f"❌ Performance tests failed: {tests_passed}/{tests_run}")
                logger.error(f"Error output: {result.stderr}")
            
            return {
                "scenario": "performance",
                "success": success,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Performance tests timed out")
            return {
                "scenario": "performance",
                "success": False,
                "error": "Timeout after 900 seconds",
                "tests_run": 0,
                "tests_passed": 0,
            }

    async def _run_docker_compose_tests(self) -> Dict[str, Any]:
        """Run Docker Compose infrastructure tests."""
        
        logger.info("🐳 Testing Docker Compose distributed infrastructure...")
        
        compose_file = Path(__file__).parent / "docker-compose.distributed-test.yml"
        
        if not compose_file.exists():
            logger.error(f"❌ Docker Compose file not found: {compose_file}")
            return {
                "scenario": "docker_compose",
                "success": False,
                "error": "Docker Compose file not found",
                "tests_run": 0,
                "tests_passed": 0,
            }
        
        try:
            # Start infrastructure
            logger.info("🚀 Starting Docker Compose infrastructure...")
            start_cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d", "--build"]
            start_result = subprocess.run(start_cmd, capture_output=True, text=True, timeout=300)
            
            if start_result.returncode != 0:
                logger.error(f"❌ Failed to start Docker Compose: {start_result.stderr}")
                return {
                    "scenario": "docker_compose",
                    "success": False,
                    "error": f"Docker Compose start failed: {start_result.stderr}",
                    "tests_run": 0,
                    "tests_passed": 0,
                }
            
            logger.info("⏳ Waiting for services to be ready...")
            await asyncio.sleep(30)  # Give services time to start
            
            # Check service health
            health_results = await self._check_docker_services_health(compose_file)
            
            # Run event generator for integration testing
            logger.info("📨 Running event generator integration test...")
            generator_result = await self._run_event_generator_test(compose_file)
            
            # Stop infrastructure
            logger.info("🛑 Stopping Docker Compose infrastructure...")
            stop_cmd = ["docker", "compose", "-f", str(compose_file), "down", "--remove-orphans"]
            subprocess.run(stop_cmd, capture_output=True, text=True, timeout=60)
            
            success = health_results["success"] and generator_result["success"]
            
            return {
                "scenario": "docker_compose",
                "success": success,
                "health_check": health_results,
                "event_generator": generator_result,
                "tests_run": health_results.get("services_checked", 0) + 1,
                "tests_passed": (health_results.get("services_healthy", 0) + 
                                (1 if generator_result["success"] else 0)),
            }
            
        except Exception as e:
            logger.error(f"❌ Docker Compose test failed: {e}")
            # Ensure cleanup
            try:
                stop_cmd = ["docker", "compose", "-f", str(compose_file), "down", "--remove-orphans"]
                subprocess.run(stop_cmd, capture_output=True, text=True, timeout=60)
            except Exception:
                pass
            
            return {
                "scenario": "docker_compose", 
                "success": False,
                "error": str(e),
                "tests_run": 0,
                "tests_passed": 0,
            }

    async def _check_docker_services_health(self, compose_file: Path) -> Dict[str, Any]:
        """Check health of Docker Compose services."""
        
        services = ["postgres", "redis", "kafka", "els_worker_1", "els_worker_2", "els_worker_3"]
        health_results = {}
        healthy_count = 0
        
        for service in services:
            try:
                # Check if service is running
                cmd = ["docker", "compose", "-f", str(compose_file), "ps", service]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if "Up" in result.stdout:
                    health_results[service] = "healthy"
                    healthy_count += 1
                    logger.info(f"✅ Service {service} is healthy")
                else:
                    health_results[service] = "unhealthy"
                    logger.warning(f"⚠️  Service {service} is not running")
                    
            except Exception as e:
                health_results[service] = f"error: {e}"
                logger.error(f"❌ Error checking service {service}: {e}")
        
        return {
            "success": healthy_count >= len(services) - 1,  # Allow one service to be down
            "services_checked": len(services),
            "services_healthy": healthy_count,
            "service_status": health_results,
        }

    async def _run_event_generator_test(self, compose_file: Path) -> Dict[str, Any]:
        """Run event generator integration test."""
        
        try:
            # Run event generator container
            cmd = [
                "docker", "compose", "-f", str(compose_file),
                "run", "--rm", "event_generator"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            success = result.returncode == 0
            
            if success:
                logger.info("✅ Event generator test passed")
            else:
                logger.error(f"❌ Event generator test failed: {result.stderr}")
            
            return {
                "success": success,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Event generator test timed out")
            return {
                "success": False,
                "error": "Timeout after 120 seconds",
            }

    def save_results(self, results: Dict[str, Any], output_file: str = "distributed_test_results.json") -> None:
        """Save test results to JSON file."""
        
        results["test_run_metadata"] = {
            "runner_version": "1.0.0",
            "total_duration": time.time() - self.start_time,
            "instances_configured": self.instances,
            "duration_configured": self.duration,
            "timestamp": time.time(),
        }
        
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📊 Test results saved to {output_file}")

    def print_summary(self, results: Dict[str, Any]) -> None:
        """Print test summary."""
        
        print("\n" + "="*80)
        print("🎯 DISTRIBUTED TEST RESULTS SUMMARY")
        print("="*80)
        
        print(f"Scenario: {results.get('scenario', 'unknown')}")
        print(f"Success: {'✅ PASS' if results.get('success', False) else '❌ FAIL'}")
        print(f"Duration: {results.get('duration', 0):.1f}s")
        
        if 'total_tests' in results:
            print(f"Total Tests: {results['total_tests']}")
            print(f"Tests Passed: {results['total_passed']}")
            print(f"Success Rate: {results.get('success_rate', 0):.1%}")
        
        if 'scenario_results' in results:
            print("\nScenario Breakdown:")
            for scenario, result in results['scenario_results'].items():
                status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
                print(f"  {scenario}: {status}")
        
        print("\n" + "="*80)


async def main() -> None:
    """Main entry point for distributed test runner."""
    
    parser = argparse.ArgumentParser(description="Run distributed tests for Essay Lifecycle Service")
    parser.add_argument("--scenario", default="all", 
                       choices=["all", "race_conditions", "redis_consistency", "performance", "docker_compose"],
                       help="Test scenario to run")
    parser.add_argument("--instances", type=int, default=3,
                       help="Number of ELS instances to simulate")
    parser.add_argument("--duration", type=int, default=60,
                       help="Test duration in seconds")
    parser.add_argument("--output", default="distributed_test_results.json",
                       help="Output file for test results")
    
    args = parser.parse_args()
    
    # Create test runner
    runner = DistributedTestRunner(instances=args.instances, duration=args.duration)
    
    try:
        # Run the specified scenario
        results = await runner.run_scenario(args.scenario)
        
        # Save and display results
        runner.save_results(results, args.output)
        runner.print_summary(results)
        
        # Exit with appropriate code
        sys.exit(0 if results.get("success", False) else 1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Test run interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())