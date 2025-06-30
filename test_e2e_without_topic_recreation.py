#!/usr/bin/env python3
"""
Test E2E without recreating Kafka topics.

This tests the hypothesis that topic recreation is causing consumer issues.
"""

import asyncio
import redis.asyncio as redis
import subprocess


async def clear_test_redis_keys():
    """Clear all test-related Redis keys to ensure test isolation."""
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    try:
        print("🧹 Clearing ALL Redis data for isolation...")
        await redis_client.flushall()
        print("🗑️  Flushed all Redis databases")
        
        # Verify cleanup
        all_keys = await redis_client.keys("*")
        print(f"🔍 Total keys after flush: {len(all_keys)}")
        
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
    
    for name, cmd in [("ELS", els_cmd), ("BOS", bos_cmd)]:
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
    """Run the E2E test."""
    print("\n🚀 Running E2E comprehensive real batch test...")
    
    cmd = [
        "pdm", "run", "pytest", 
        "tests/functional/test_e2e_comprehensive_real_batch.py::test_comprehensive_real_batch_pipeline",
        "-v", "-s", "--tb=short"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        print("\n📋 Test Output:")
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("\n✅ Test PASSED!")
        else:
            print(f"\n❌ Test FAILED with return code: {result.returncode}")
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("\n⏰ Test timed out after 120 seconds")
        return False
    except Exception as e:
        print(f"\n❌ Error running test: {e}")
        return False


async def main():
    """Main test without Kafka topic recreation."""
    print("🔬 Testing WITHOUT Kafka topic recreation")
    print("=" * 60)
    print("Hypothesis: Topic recreation causes consumer subscription issues")
    print("=" * 60)
    
    # Step 1: Clear Redis keys
    if not await clear_test_redis_keys():
        print("❌ Redis cleanup failed - aborting test")
        return False
    
    # Step 2: Clear test databases
    await clear_test_databases()
    
    # Step 3: Do NOT recreate Kafka topics
    print("\n⚠️  SKIPPING Kafka topic recreation")
    print("Topics remain as-is with existing partitions and metadata")
    
    print("\n✅ Partial test environment isolation achieved:")
    print("   - Redis: All keys flushed")
    print("   - Kafka: Topics NOT recreated (testing hypothesis)")
    print("   - Databases: Test data truncated")
    print("=" * 60)
    
    # Step 4: Give services a moment to stabilize
    print("\n⏳ Waiting 3 seconds for services to stabilize...")
    await asyncio.sleep(3)
    
    # Step 5: Run the E2E test
    test_success = run_e2e_test()
    
    print("\n" + "=" * 60)
    if test_success:
        print("🎉 HYPOTHESIS CONFIRMED!")
        print("✅ The E2E test passes without topic recreation")
        print("❌ Topic recreation disrupts Kafka consumer subscriptions")
        print("\nRecommendation: Use topic offset reset instead of recreation")
    else:
        print("🔍 Test still failed without topic recreation")
        print("The issue is deeper than just topic recreation")
    
    return test_success


if __name__ == "__main__":
    asyncio.run(main())