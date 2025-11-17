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
        output_file = str(md_path.with_suffix(".pdf"))

    # Get the directory containing this script
    script_dir = Path(__file__).parent
    filter_path = script_dir / "mermaid_filter.lua"

    if not filter_path.exists():
        print(f"Error: Mermaid filter not found at {filter_path}")
        return False

    # Build pandoc command
    css_path = script_dir / "pdf_toc_style.css"
    cmd = [
        "pandoc",
        str(md_path),
        f"--lua-filter={filter_path}",
        "--toc",  # Include table of contents
        "--metadata",
        "toc-title=Innehållsförteckning",  # Custom TOC title
        f"--css={css_path}",  # Custom TOC and PDF styles
        "--pdf-engine=weasyprint",  # Use weasyprint instead of LaTeX
        # Add specific WeasyPrint parameters to control diagram sizing and page breaks
        "--variable",
        "papersize=a4",
        "--variable",
        "geometry:margin=2cm",
        "--variable",
        "fontsize=10pt",
        # Add HTML options to control page breaks
        "--epub-embed-font=Arial",  # Force embed fonts
        "--html-q-tags",  # Use quotes for quotes
        "--variable",
        "documentclass=report",  # More compact spacing
        "-o",
        str(output_file),
    ]

    # Define HTML output file for debugging structure
    html_output_file = str(md_path.with_name(md_path.stem + "_debug.html"))

    # Command to generate intermediate HTML (without WeasyPrint, using Pandoc's default HTML writer)
    html_cmd = [
        "pandoc",
        str(md_path),
        f"--lua-filter={filter_path}",
        "--toc",  # Keep TOC for structure
        "--metadata",
        "toc-title=Innehållsförteckning",  # Keep custom TOC title
        "--standalone",  # Ensure full HTML document
        "--self-contained",  # Embed assets if any, for easier viewing (optional)
        "-o",
        html_output_file,
    ]
    print(f"Generating intermediate HTML: {html_output_file}...")
    print(f"HTML Command: {' '.join(html_cmd)}")
    try:
        html_result = subprocess.run(html_cmd, capture_output=True, text=True, check=False)
        if html_result.returncode == 0:
            print(f"✅ Successfully generated intermediate HTML: {html_output_file}")
        else:
            print("❌ Error during intermediate HTML generation:")
            print(f"STDOUT: {html_result.stdout}")
            print(f"STDERR: {html_result.stderr}")
            # Continue to PDF generation even if HTML debug fails, but notify
    except Exception as e_html:
        print(f"❌ Unexpected error during intermediate HTML generation: {e_html}")

    # Proceed with PDF generation
    print(f"Converting {md_file} to {output_file} (PDF)...")
    print(f"PDF Command: {' '.join(cmd)}")  # cmd is the original PDF command

    try:
        pdf_result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if pdf_result.returncode == 0:
            print(f"✅ Successfully converted to {output_file} (PDF)")
            return True
        else:
            print("❌ Error during PDF conversion:")
            print(f"STDOUT: {pdf_result.stdout}")
            print(f"STDERR: {pdf_result.stderr}")
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
