#!/usr/bin/env python3
"""
Markdown to PDF Converter Script

This script converts markdown files to PDF using a two-step process:
1. Markdown → HTML (using pypandoc)
2. HTML → PDF (using weasyprint)

Features:
- Proper UTF-8 character encoding handling
- Error handling and validation
- Configurable CSS styling
- Support for custom output paths
- Logging for debugging
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

try:
    import pypandoc
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Please install with: pdm add pypandoc weasyprint")
    sys.exit(1)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )


def validate_input_file(input_path: Path) -> None:
    """Validate that the input markdown file exists and is readable."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if input_path.suffix.lower() not in [".md", ".markdown"]:
        logging.warning(f"Input file does not have a markdown extension: {input_path}")


def get_default_css() -> str:
    """Return default CSS styling for the PDF output."""
    return """
    @page {
        size: A4;
        margin: 1.5cm 2cm;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 10pt;
        line-height: 1.4;
        color: #333;
        max-width: none;
        text-align: left;
    }

    /* Professional title page styling */
    header h1:first-of-type {
        font-size: 2.2em;
        color: #1a365d;
        text-align: left;
        margin: 0 0 0.5em 0;
        padding: 0;
        border: none;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    /* Remove pandoc's default title centering */
    .title {
        text-align: left !important;
        margin: 0 !important;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #2c3e50;
        margin-top: 1.2em;
        margin-bottom: 0.4em;
        font-weight: 600;
        text-align: left;
    }

    h1 {
        font-size: 1.6em;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.2em;
        margin-top: 1.5em;
    }

    h2 {
        font-size: 1.3em;
        border-bottom: 1px solid #bdc3c7;
        padding-bottom: 0.15em;
        margin-top: 1.3em;
    }

    h3 {
        font-size: 1.15em;
        margin-top: 1.1em;
    }

    h4 {
        font-size: 1.05em;
        margin-top: 1em;
    }

    h5, h6 {
        font-size: 1em;
        margin-top: 0.9em;
    }

    p {
        margin: 0.6em 0;
        text-align: justify;
    }

    code {
        background-color: #f8f9fa;
        padding: 0.15em 0.3em;
        border-radius: 2px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 0.85em;
        border: 1px solid #e9ecef;
    }

    pre {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 4px;
        padding: 0.8em;
        margin: 0.8em 0;
        font-size: 0.8em;
        line-height: 1.3;
    }

    pre code {
        background-color: transparent;
        padding: 0;
        border: none;
    }

    table {
        border-collapse: collapse;
        width: 100%;
        margin: 0.8em 0;
        font-size: 0.9em;
    }

    th, td {
        border: 1px solid #ddd;
        padding: 0.4em 0.6em;
        text-align: left;
        vertical-align: top;
    }

    th {
        background-color: #f8f9fa;
        font-weight: 600;
    }

    blockquote {
        border-left: 3px solid #3498db;
        margin: 0.8em 0;
        padding-left: 1em;
        color: #666;
        font-style: italic;
        background-color: #f9f9f9;
        padding: 0.5em 0.5em 0.5em 1em;
    }

    ul, ol {
        margin: 0.6em 0;
        padding-left: 1.5em;
    }

    li {
        margin: 0.2em 0;
        line-height: 1.3;
    }

    /* Nested lists with tighter spacing */
    li ul, li ol {
        margin: 0.3em 0;
    }

    a {
        color: #3498db;
        text-decoration: none;
    }

    a:hover {
        text-decoration: underline;
    }

    /* Compact spacing for definition lists */
    dl {
        margin: 0.6em 0;
    }

    dt {
        font-weight: 600;
        margin-top: 0.4em;
    }

    dd {
        margin-left: 1.5em;
        margin-bottom: 0.4em;
    }

    /* Page break utilities */
    .page-break {
        page-break-before: always;
    }

    /* Avoid breaking inside these elements */
    h1, h2, h3, h4, h5, h6 {
        page-break-after: avoid;
    }

    table, pre, blockquote {
        page-break-inside: avoid;
    }

    /* Orphan and widow control */
    p {
        orphans: 2;
        widows: 2;
    }
    """


def markdown_to_html(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    Convert markdown file to HTML using pypandoc.

    Args:
        input_path: Path to the input markdown file
        output_path: Optional path for HTML output (defaults to input_path with .html extension)

    Returns:
        Path to the generated HTML file
    """
    if output_path is None:
        output_path = input_path.with_suffix(".html")

    logging.info(f"Converting markdown to HTML: {input_path} → {output_path}")

    try:
        # Use pypandoc with explicit UTF-8 encoding
        pypandoc.convert_file(
            str(input_path),
            "html",
            outputfile=str(output_path),
            extra_args=[
                "--standalone",  # Include HTML document structure
                "--metadata",
                "title=" + input_path.stem,
                "--from=markdown+smart",  # Enable smart typography
                "--to=html5",
            ],
        )

        # Verify the HTML file was created and has content
        if not output_path.exists():
            raise RuntimeError("HTML file was not created")

        if output_path.stat().st_size == 0:
            raise RuntimeError("HTML file is empty")

        logging.info(f"Successfully created HTML file: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Failed to convert markdown to HTML: {e}")
        raise


def html_to_pdf(
    html_path: Path, output_path: Optional[Path] = None, css_content: Optional[str] = None
) -> Path:
    """
    Convert HTML file to PDF using weasyprint.

    Args:
        html_path: Path to the input HTML file
        output_path: Optional path for PDF output (defaults to html_path with .pdf extension)
        css_content: Optional CSS styling content

    Returns:
        Path to the generated PDF file
    """
    if output_path is None:
        output_path = html_path.with_suffix(".pdf")

    if css_content is None:
        css_content = get_default_css()

    logging.info(f"Converting HTML to PDF: {html_path} → {output_path}")

    try:
        # Create font configuration for better font handling
        font_config = FontConfiguration()

        # Read HTML content with explicit UTF-8 encoding
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Create HTML and CSS objects
        html_doc = HTML(string=html_content, base_url=str(html_path.parent))
        css_doc = CSS(string=css_content, font_config=font_config)

        # Generate PDF
        html_doc.write_pdf(str(output_path), stylesheets=[css_doc], font_config=font_config)

        # Verify the PDF file was created and has content
        if not output_path.exists():
            raise RuntimeError("PDF file was not created")

        if output_path.stat().st_size == 0:
            raise RuntimeError("PDF file is empty")

        logging.info(f"Successfully created PDF file: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Failed to convert HTML to PDF: {e}")
        raise


def convert_markdown_to_pdf(
    input_path: Path,
    output_path: Optional[Path] = None,
    keep_html: bool = False,
    css_file: Optional[Path] = None,
    verbose: bool = False,
) -> Path:
    """
    Convert markdown file to PDF via HTML intermediate step.

    Args:
        input_path: Path to the input markdown file
        output_path: Optional path for PDF output
        keep_html: Whether to keep the intermediate HTML file
        css_file: Optional path to custom CSS file
        verbose: Enable verbose logging

    Returns:
        Path to the generated PDF file
    """
    setup_logging(verbose)

    # Validate input
    validate_input_file(input_path)

    # Determine output paths
    if output_path is None:
        output_path = input_path.with_suffix(".pdf")

    html_path = input_path.with_suffix(".html")

    # Load custom CSS if provided
    css_content = None
    if css_file and css_file.exists():
        logging.info(f"Loading custom CSS from: {css_file}")
        with open(css_file, "r", encoding="utf-8") as f:
            css_content = f.read()

    try:
        # Step 1: Markdown → HTML
        html_path = markdown_to_html(input_path, html_path)

        # Step 2: HTML → PDF
        pdf_path = html_to_pdf(html_path, output_path, css_content)

        # Clean up intermediate HTML file if not requested to keep
        if not keep_html and html_path.exists():
            html_path.unlink()
            logging.info(f"Removed intermediate HTML file: {html_path}")

        return pdf_path

    except Exception:
        # Clean up on error
        if html_path.exists() and not keep_html:
            html_path.unlink()
        raise


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Convert markdown files to PDF via HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s README.md
  %(prog)s README.md -o documentation.pdf
  %(prog)s README.md --keep-html --verbose
  %(prog)s README.md --css custom.css
        """,
    )

    parser.add_argument("input", type=Path, help="Input markdown file path")

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output PDF file path (default: input file with .pdf extension)",
    )

    parser.add_argument("--keep-html", action="store_true", help="Keep intermediate HTML file")

    parser.add_argument("--css", type=Path, help="Path to custom CSS file for styling")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    try:
        pdf_path = convert_markdown_to_pdf(
            input_path=args.input,
            output_path=args.output,
            keep_html=args.keep_html,
            css_file=args.css,
            verbose=args.verbose,
        )

        print(f"✅ Successfully converted to PDF: {pdf_path}")

    except Exception as e:
        print(f"❌ Conversion failed: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
