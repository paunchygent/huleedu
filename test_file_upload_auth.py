#!/usr/bin/env python3
"""
Test file upload with proper authentication.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.utils.test_auth_manager import AuthTestManager
from tests.utils.service_test_manager import ServiceTestManager


async def test_file_upload_with_auth():
    """Test file upload with proper authentication."""
    
    print("🔐 Setting up authentication...")
    auth_manager = AuthTestManager()
    service_manager = ServiceTestManager(auth_manager=auth_manager)
    
    # Create a test teacher user
    test_teacher = auth_manager.create_teacher_user("Test Teacher")
    print(f"✅ Created test user: {test_teacher.name} (ID: {test_teacher.user_id})")
    
    # Validate services are healthy
    print("\n🏥 Checking service health...")
    endpoints = await service_manager.get_validated_endpoints()
    print(f"✅ {len(endpoints)} services validated healthy")
    
    # Create a test batch
    print("\n📝 Creating test batch...")
    batch_id = str(uuid4())
    correlation_id = str(uuid4())
    
    # Register batch with BOS
    batch_creation_payload = {
        "expected_essay_count": 1,
        "course_code": "ENG5",
        "essay_instructions": "Write a test essay for authentication testing",
        "user_id": test_teacher.user_id,
        "enable_cj_assessment": False
    }
    
    # Get BOS endpoint
    bos_base = endpoints["batch_orchestrator_service"]["base_url"]
    
    import aiohttp
    async with aiohttp.ClientSession() as session:
        # Get auth headers
        auth_headers = auth_manager.get_auth_headers(test_teacher)
        headers = auth_headers.copy()
        headers["X-Correlation-ID"] = correlation_id
        
        # Create batch
        async with session.post(
            f"{bos_base}/v1/batches/register",
            json=batch_creation_payload,
            headers=headers
        ) as response:
            if response.status not in [200, 202]:
                text = await response.text()
                print(f"❌ Batch creation failed: {response.status} - {text}")
                return False
            
            batch_data = await response.json()
            batch_id = batch_data["batch_id"]
            print(f"✅ Batch created: {batch_id}")
    
    # Create a simple test file
    print("\n📄 Creating test file...")
    test_content = "This is a test essay. It has some content to test the upload."
    test_file = {
        "name": "test_essay.txt",
        "content": test_content.encode('utf-8')
    }
    
    # Upload the file
    print("\n📤 Uploading file with authentication...")
    try:
        upload_result = await service_manager.upload_files(
            batch_id=batch_id,
            files=[test_file],
            user=test_teacher,
            correlation_id=correlation_id
        )
        
        print(f"✅ File upload successful!")
        print(f"📊 Upload result: {upload_result}")
        
        # Check if we got essay IDs
        if "essay_ids" in upload_result:
            print(f"✅ Got essay IDs: {upload_result['essay_ids']}")
        
        return True
        
    except Exception as e:
        print(f"❌ File upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the file upload authentication test."""
    print("🔐 Testing File Upload with Authentication")
    print("=" * 50)
    
    success = await test_file_upload_with_auth()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ File upload authentication test PASSED!")
    else:
        print("❌ File upload authentication test FAILED")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())