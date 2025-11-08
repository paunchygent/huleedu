#!/usr/bin/env bash
# Remove macOS quarantine attributes from repository files
# This fixes "permission denied" errors in git hooks caused by com.apple.provenance

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "🔍 Scanning for quarantine attributes in repository..."

# Find all files and directories with com.apple.provenance attribute
QUARANTINED_ITEMS=$(find . -type f -o -type d | xargs xattr -l 2>/dev/null | grep -B1 "com.apple.provenance" | grep -v "^--$" | grep -v "com.apple.provenance" | sed 's/:$//' || true)

if [ -z "$QUARANTINED_ITEMS" ]; then
    echo "✅ No quarantine attributes found. Repository is clean!"
    exit 0
fi

echo "📋 Found quarantined items:"
echo "$QUARANTINED_ITEMS"
echo ""
echo "🧹 Removing quarantine attributes..."

# Remove quarantine attributes recursively from entire repo
xattr -dr com.apple.provenance . 2>/dev/null || true

echo "✅ Quarantine attributes removed!"
echo ""
echo "🔍 Verifying cleanup..."

# Verify removal
REMAINING=$(find . -type f -o -type d | xargs xattr -l 2>/dev/null | grep "com.apple.provenance" || true)

if [ -z "$REMAINING" ]; then
    echo "✅ Verification successful! All quarantine attributes removed."
else
    echo "⚠️  Some items still have quarantine attributes:"
    echo "$REMAINING"
    exit 1
fi
