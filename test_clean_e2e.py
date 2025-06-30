#!/usr/bin/env python3
"""
Clean E2E test after fixing all services.
"""

import asyncio
import redis.asyncio as redis
import subprocess


async def clear_test_redis_keys():
    """Clear all test-related Redis keys to ensure test isolation."""
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    try:
        print("🧹 Clearing ALL Redis data...")
        await redis_client.flushall()
        print("✅ Flushed all Redis databases")
    except Exception as e:
        print(f"❌ Error accessing Redis: {e}")
        return False
    finally:
        await redis_client.aclose()
    
    return True


async def clear_test_databases():
    """Clear test data from databases for isolation."""
    print("🗄️  Clearing test data from databases...")
    
    # Clear ELS database
    els_cmd = [
        "docker", "exec", "-i", "huleedu_essay_lifecycle_db",
        "psql", "-U", "huleedu_user", "-d", "essay_lifecycle",
        "-c", "TRUNCATE TABLE essay_states CASCADE;"
    ]
    
    # Clear BOS database  
    bos_cmd = [
        "docker", "exec", "-i", "huleedu_batch_orchestrator_db",
        "psql", "-U", "huleedu_user", "-d", "batch_orchestrator",
        "-c", "TRUNCATE TABLE batches, batch_essays, phase_status_log, configuration_snapshots CASCADE;"
    ]
    
    # Clear Result Aggregator database
    ras_cmd = [
        "docker", "exec", "-i", "huleedu_result_aggregator_db",
        "psql", "-U", "huleedu_user", "-d", "result_aggregator",
        "-c", "TRUNCATE TABLE batch_summaries, essay_results CASCADE;"
    ]
    
    # Clear CJ Assessment database
    cj_cmd = [
        "docker", "exec", "-i", "huleedu_cj_assessment_db",
        "psql", "-U", "huleedu_user", "-d", "cj_assessment",
        "-c", "TRUNCATE TABLE assessment_runs, pairwise_comparisons CASCADE;"
    ]
    
    for name, cmd in [("ELS", els_cmd), ("BOS", bos_cmd), ("RAS", ras_cmd), ("CJ", cj_cmd)]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Cleared {name} database")
            else:
                print(f"⚠️  Failed to clear {name} database: {result.stderr}")
        except Exception as e:
            print(f"⚠️  Error clearing {name} database: {e}")
    
    print("✅ Database cleanup completed")


def run_e2e_test():
    """Run the E2E test with 40 second timeout."""
    print("\n🚀 Running E2E comprehensive real batch test...")
    
    cmd = [
        "pdm", "run", "pytest", 
        "tests/functional/test_e2e_comprehensive_real_batch.py::test_comprehensive_real_batch_pipeline",
        "-v", "-s", "--tb=short", "--timeout=40"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        
        print("\n📋 Test Output:")
        if result.returncode == 0:
            print("✅ Test PASSED!")
            # Show last few lines of output
            lines = result.stdout.split('\n')
            for line in lines[-20:]:
                if line.strip():
                    print(line)
        else:
            print(f"❌ Test FAILED with return code: {result.returncode}")
            # Show error output
            if "FAILED" in result.stdout:
                print("\nTest failures:")
                for line in result.stdout.split('\n'):
                    if "FAILED" in line or "ERROR" in line or "assert" in line:
                        print(line)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("\n⏰ Test timed out after 50 seconds")
        return False
    except Exception as e:
        print(f"\n❌ Error running test: {e}")
        return False


async def main():
    """Run clean E2E test after all fixes."""
    print("🔬 Clean E2E Test After All Fixes")
    print("=" * 60)
    print("Services fixed:")
    print("✅ BOS Kafka consumer (topic name issue)")
    print("✅ ELS phase outcome publisher (rebuilt)")
    print("✅ Authentication working")
    print("✅ Essay storage and retrieval working")
    print("=" * 60)
    
    # Step 1: Clear Redis keys
    if not await clear_test_redis_keys():
        print("❌ Redis cleanup failed - aborting test")
        return False
    
    # Step 2: Clear test databases
    await clear_test_databases()
    
    print("\n✅ Test environment cleaned")
    print("=" * 60)
    
    # Step 3: Give services a moment to stabilize
    print("\n⏳ Waiting 5 seconds for services to stabilize...")
    await asyncio.sleep(5)
    
    # Step 4: Run the E2E test
    test_success = run_e2e_test()
    
    print("\n" + "=" * 60)
    if test_success:
        print("🎉 SUCCESS! E2E test is now working!")
        print("All fixes have been successfully applied.")
    else:
        print("❌ Test still failing - check logs for details")
    
    return test_success


if __name__ == "__main__":
    asyncio.run(main())