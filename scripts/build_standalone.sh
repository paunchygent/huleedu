#!/bin/bash
set -e

echo "Building standalone executable with PyInstaller 6.16.0..."

# Clean previous builds
rm -rf build/ dist/

# Build TUI
echo "Building redistribute-tui..."
pdm run pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name redistribute-tui \
  --distpath ./dist \
  --workpath ./build \
  scripts/bayesian_consensus_model/redistribute_tui.py

# Smoke tests
echo ""
echo "Running smoke tests..."

# Test redistribute-tui (verify it exists and is executable)
if [ ! -x "./dist/redistribute-tui" ]; then
    echo "ERROR: redistribute-tui is not executable"
    exit 1
fi
echo "✓ redistribute-tui is executable"

echo ""
echo "✅ Build complete!"
echo "Executable:"
echo "  - dist/redistribute-tui"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/redistribute-tui /usr/local/bin/"
