#!/usr/bin/env python3
"""
Test E2E with proper authentication setup.
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import authentication utilities
from tests.libs.e2e_utils.auth_test_manager import AuthTestManager
from tests.libs.e2e_utils.service_test_utils import ServiceTestUtils

# Import batch management utilities
from tests.libs.e2e_utils.real_batch_executor import RealBatchExecutor
from tests.libs.e2e_utils.batch_monitor import BatchMonitor
from tests.libs.e2e_utils.events.batch_event_collector import BatchEventCollector

# Import file upload utilities
from tests.libs.e2e_utils.file_uploads import FileUploadManager
from tests.libs.e2e_utils.dummy_file_generator import (
    DummyFileGenerator, 
    FileType,
    WriteFrequency,
    WriteStyle
)


async def test_with_authentication():
    """Run a minimal E2E test with proper authentication."""
    
    print("🔐 Setting up authentication...")
    auth_manager = AuthTestManager()
    utils = ServiceTestUtils()
    
    # Create a test user with proper credentials
    test_user = await auth_manager.create_test_user(
        username="test_user_auth",
        email="test@example.com",
        role="teacher"
    )
    
    # Get authentication token
    token = await auth_manager.get_auth_token(test_user["user_id"])
    
    print(f"✅ Created test user: {test_user['username']} (ID: {test_user['user_id']})")
    print(f"🔑 Got auth token: {token[:20]}...")
    
    # Initialize batch components
    batch_executor = RealBatchExecutor(auth_manager=auth_manager)
    monitor = BatchMonitor()
    event_collector = BatchEventCollector()
    file_upload_manager = FileUploadManager()
    
    try:
        # Generate test files
        print("\n📝 Generating test essay files...")
        generator = DummyFileGenerator(total_mb=1)
        essay_files = generator.generate_files(
            count=2,
            file_type=FileType.ESSAY,
            write_frequency=WriteFrequency.WORD,
            write_style=WriteStyle.STANDARD,
            misspelling_percentage=5
        )
        
        # Start monitoring
        monitor_task = asyncio.create_task(event_collector.monitor_batch_events())
        
        # Create batch with authentication
        print("\n🚀 Creating batch with authentication...")
        batch_data = await batch_executor.create_batch(
            title="Auth Test Batch",
            description="Testing with proper authentication",
            class_id=str(uuid4()),
            user_token=token  # Pass the auth token
        )
        
        batch_id = batch_data["batch_id"]
        correlation_id = batch_data["correlation_id"]
        
        print(f"✅ Batch created: {batch_id}")
        print(f"📋 Correlation ID: {correlation_id}")
        
        # Upload essays with authentication
        print("\n📤 Uploading essays with authentication...")
        essay_ids = []
        
        for idx, essay_file in enumerate(essay_files):
            print(f"  Uploading essay {idx + 1}/{len(essay_files)}...", end="", flush=True)
            
            # Upload with authentication token
            essay_data = await file_upload_manager.upload_essay(
                file_path=essay_file,
                batch_id=batch_id,
                student_name=f"Student {idx + 1}",
                auth_token=token  # Pass auth token for upload
            )
            
            essay_ids.append(essay_data["essay_id"])
            print(f" ✅ (ID: {essay_data['essay_id']})")
        
        print(f"\n✅ Uploaded {len(essay_ids)} essays successfully!")
        
        # Register essays with batch
        print("\n📋 Registering essays with batch...")
        registration_result = await batch_executor.register_essays_with_batch(
            batch_id=batch_id,
            essay_ids=essay_ids,
            user_token=token  # Pass auth token
        )
        
        print(f"✅ Registration result: {registration_result}")
        
        # Wait for pipeline completion
        print("\n⏳ Waiting for pipeline to complete (max 30s)...")
        
        try:
            pipeline_result = await asyncio.wait_for(
                monitor.wait_for_completion(batch_id),
                timeout=30
            )
            
            print(f"✅ Pipeline completed successfully!")
            print(f"📊 Result: {pipeline_result}")
            
        except asyncio.TimeoutError:
            print("❌ Pipeline timed out after 30 seconds")
            
            # Check what events were captured
            events = event_collector.get_all_events()
            print(f"\n📋 Captured {len(events)} events:")
            for event in events[-10:]:  # Show last 10 events
                print(f"  - {event.get('event_type', 'Unknown')}")
            
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        # Cleanup
        generator.cleanup()


async def main():
    """Run the authentication test."""
    print("🔐 Testing E2E with proper authentication")
    print("=" * 50)
    
    success = await test_with_authentication()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Authentication test PASSED!")
        print("The issue was indeed authentication for file uploads.")
    else:
        print("❌ Authentication test FAILED")
        print("There may be additional issues beyond authentication.")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())