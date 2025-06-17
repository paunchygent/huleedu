#!/usr/bin/env python3
"""
Convert Markdown to PDF using pandoc with Mermaid diagram support.
Uses subprocess to call pandoc directly with the mermaid_filter.lua.
"""

import subprocess
import sys
from pathlib import Path


def convert_md_to_pdf(md_file: str, output_file: str | None = None):
    """Convert markdown file to PDF using pandoc with mermaid filter."""

    md_path = Path(md_file)
    if not md_path.exists():
        print(f"Error: File {md_file} not found")
        return False

    if output_file is None:
        output_file = str(md_path.with_suffix('.pdf'))

    # Get the directory containing this script
    script_dir = Path(__file__).parent
    filter_path = script_dir / "mermaid_filter.lua"

    if not filter_path.exists():
        print(f"Error: Mermaid filter not found at {filter_path}")
        return False

    # Build pandoc command
    cmd = [
        "pandoc",
        str(md_path),
        f"--lua-filter={filter_path}",
        "--pdf-engine=weasyprint",  # Use weasyprint instead of LaTeX
        "-o", str(output_file)
    ]

    print(f"Converting {md_file} to {output_file}...")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=script_dir)

        if result.returncode == 0:
            print(f"✅ Successfully converted to {output_file}")
            return True
        else:
            print("❌ Error during conversion:")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False

    except FileNotFoundError:
        print("❌ Error: pandoc not found. Please install pandoc first:")
        print("   brew install pandoc")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_to_pdf.py <markdown_file> [output_file]")
        sys.exit(1)

    md_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    success = convert_md_to_pdf(md_file, output_file)
    sys.exit(0 if success else 1)
