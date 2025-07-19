#!/usr/bin/env python3
"""
Test script to verify API Gateway authentication is working properly.
"""

import asyncio
from datetime import datetime, timedelta

import httpx
import jwt

# Test configuration
GATEWAY_URL = "http://localhost:8080"
JWT_SECRET = "a-very-secret-key-that-must-be-in-secrets-manager"  # Should match your settings
JWT_ALGORITHM = "HS256"


def create_test_token(user_id: str = "test-user-123", expires_in: int = 300) -> str:
    """Create a test JWT token."""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(seconds=expires_in),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def test_no_auth():
    """Test endpoint without authentication."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/test/no-auth")
            print(f"No auth test: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"No auth test error: {e}")
            return False


async def test_with_valid_auth():
    """Test endpoint with valid authentication."""
    token = create_test_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/test/with-auth", headers=headers)
            print(f"\nValid auth test: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"Valid auth test error: {e}")
            return False


async def test_missing_auth():
    """Test endpoint with missing authentication."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/test/with-auth")
            print(f"\nMissing auth test: {response.status_code}")
            print(f"Response: {response.json()}")
            # Should return 401 with HuleEduError format
            return response.status_code == 401
        except Exception as e:
            print(f"Missing auth test error: {e}")
            return False


async def test_expired_token():
    """Test endpoint with expired token."""
    token = create_test_token(expires_in=-300)  # Already expired
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/test/with-auth", headers=headers)
            print(f"\nExpired token test: {response.status_code}")
            print(f"Response: {response.json()}")
            # Should return 401 with HuleEduError format
            return response.status_code == 401
        except Exception as e:
            print(f"Expired token test error: {e}")
            return False


async def test_batch_status():
    """Test batch status endpoint with authentication."""
    token = create_test_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{GATEWAY_URL}/v1/batches/test-batch-123/status", headers=headers
            )
            print(f"\nBatch status test: {response.status_code}")
            print(f"Response: {response.json()}")
            # Might be 404 if batch doesn't exist, but auth should work
            return response.status_code in (200, 404)
        except Exception as e:
            print(f"Batch status test error: {e}")
            return False


async def main():
    print("Testing API Gateway Authentication...")
    print("=" * 50)

    tests = [
        ("No Auth Required", test_no_auth),
        ("Valid Authentication", test_with_valid_auth),
        ("Missing Authentication", test_missing_auth),
        ("Expired Token", test_expired_token),
        ("Batch Status with Auth", test_batch_status),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        result = await test_func()
        results.append((test_name, result))

    print("\n" + "=" * 50)
    print("Test Results:")
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")


if __name__ == "__main__":
    asyncio.run(main())
