#!/bin/bash

echo "Testing file_service build with different approaches..."

# Test 1: Try with increased Docker memory (if possible)
echo "=== Test 1: Current approach with explicit memory limit ==="
docker build \
  --memory="4g" \
  --memory-swap="4g" \
  -f services/file_service/Dockerfile \
  -t file_service_test1 \
  . 2>&1 | tee build_test1.log

if [ $? -eq 0 ]; then
    echo "✅ Test 1 PASSED: Build succeeded with increased memory"
else
    echo "❌ Test 1 FAILED: Build failed even with increased memory"
fi

# Test 2: Try with pdm.lock included (temporarily modify .dockerignore)
echo "=== Test 2: With pdm.lock included ==="
cp .dockerignore .dockerignore.bak
sed -i.tmp '/^pdm.lock/d' .dockerignore

# Also need to ensure the Dockerfile copies it (already done)
docker build \
  -f services/file_service/Dockerfile \
  -t file_service_test2 \
  . 2>&1 | tee build_test2.log

# Restore .dockerignore
mv .dockerignore.bak .dockerignore
rm .dockerignore.tmp

if [ $? -eq 0 ]; then
    echo "✅ Test 2 PASSED: Build succeeded with pdm.lock"
else
    echo "❌ Test 2 FAILED: Build failed even with pdm.lock"
fi

echo "Tests complete. Check build_test1.log and build_test2.log for details."