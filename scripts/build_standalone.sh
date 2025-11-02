#!/bin/bash
set -e

echo "Building standalone executable with PyInstaller 6.16.0..."

# Clean previous builds
rm -rf build/ dist/

# Build TUI
echo "Building cj-pair-generator-tui..."
pdm run pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name cj-pair-generator-tui \
  --distpath ./dist \
  --workpath ./build \
  scripts/bayesian_consensus_model/redistribute_tui.py

# Smoke tests
echo ""
echo "Running smoke tests..."

# Test cj-pair-generator-tui (verify it exists and is executable)
if [ ! -x "./dist/cj-pair-generator-tui" ]; then
    echo "ERROR: cj-pair-generator-tui is not executable"
    exit 1
fi
echo "✓ cj-pair-generator-tui is executable"

echo ""
echo "✅ Build complete!"
echo "Executable:"
echo "  - dist/cj-pair-generator-tui"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/cj-pair-generator-tui /usr/local/bin/"
