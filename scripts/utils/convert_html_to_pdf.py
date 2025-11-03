#!/usr/bin/env python3
"""
HTML to PDF Converter Script

This script converts HTML files to PDF with proper CSS preservation and image embedding.
Supports multiple backends with automatic fallback.

Features:
- Primary: WeasyPrint for excellent CSS support
- Fallback: pypandoc for basic conversion
- Proper UTF-8 character encoding
- Image embedding from relative paths
- Configurable page layout and margins
- Swedish character support
- Error handling and validation
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple

# Check for weasyprint availability (primary backend)
try:
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logging.info("WeasyPrint not available, will use pypandoc fallback")

# pypandoc should always be available (already in project dependencies)
try:
    import pypandoc

    PYPANDOC_AVAILABLE = True
except ImportError:
    PYPANDOC_AVAILABLE = False
    logging.warning("pypandoc not available")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )


def validate_html_file(input_path: Path) -> None:
    """
    Validate that the input HTML file exists and is readable.
    Also check for referenced images in the same directory.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if input_path.suffix.lower() not in [".html", ".htm"]:
        logging.warning(f"Input file may not be HTML: {input_path}")

    # Check for images in the same directory (common for HTML with embedded images)
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg"}
    images_found = []
    for img_file in input_path.parent.glob("*"):
        if img_file.suffix.lower() in image_extensions:
            images_found.append(img_file.name)

    if images_found:
        logging.info(
            f"Found {len(images_found)} image(s) in same directory: {', '.join(images_found)}"
        )


def get_supplementary_css() -> str:
    """
    Return supplementary CSS for better PDF rendering.
    This CSS enhances the existing HTML styling without overriding it.
    """
    return """
    @page {
        size: A4;
        margin: 15mm 20mm;
    }

    /* For print/PDF: optimize layout */
    @media print {
        body {
            margin: 0;
            padding: 0;
            background: white;
        }

        .container {
            margin: 0;
            padding: 0;
            width: 100%;
            max-width: 100%;
            border-radius: 0;
        }
    }

    /* Ensure images fit within page */
    img {
        max-width: 100%;
        height: auto;
        page-break-inside: avoid;
    }

    /* Better page break control */
    h1, h2, h3, h4, h5, h6 {
        page-break-after: avoid;
    }

    table {
        page-break-inside: avoid;
    }

    tr {
        page-break-inside: avoid;
        page-break-after: auto;
    }

    /* Avoid orphans and widows */
    p, li {
        orphans: 3;
        widows: 3;
    }

    /* Ensure figure captions stay with figures */
    .figure {
        page-break-inside: avoid;
    }

    .figure-caption {
        page-break-before: avoid;
    }

    /* Boxes should not break */
    .highlight, .recommendation, .warning {
        page-break-inside: avoid;
    }
    """


def convert_with_weasyprint(
    html_path: Path, output_path: Path, add_supplementary_css: bool = True
) -> Path:
    """
    Convert HTML to PDF using WeasyPrint (best CSS support).

    Args:
        html_path: Path to input HTML file
        output_path: Path for output PDF file
        add_supplementary_css: Whether to add supplementary CSS for better rendering

    Returns:
        Path to generated PDF file
    """
    if not WEASYPRINT_AVAILABLE:
        raise ImportError("WeasyPrint is not installed. Run: pdm add weasyprint")

    logging.info(f"Converting with WeasyPrint: {html_path} → {output_path}")

    try:
        # Create font configuration
        font_config = FontConfiguration()

        # Read HTML content with UTF-8 encoding
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Create HTML object with proper base URL for relative image paths
        html_doc = HTML(string=html_content, base_url=str(html_path.parent.absolute()) + "/")

        # Prepare stylesheets
        stylesheets = []
        if add_supplementary_css:
            css_doc = CSS(string=get_supplementary_css(), font_config=font_config)
            stylesheets.append(css_doc)

        # Generate PDF
        html_doc.write_pdf(str(output_path), stylesheets=stylesheets, font_config=font_config)

        # Verify PDF was created
        if not output_path.exists():
            raise RuntimeError("PDF file was not created")

        if output_path.stat().st_size == 0:
            raise RuntimeError("PDF file is empty")

        logging.info(
            f"Successfully created PDF: {output_path} ({output_path.stat().st_size:,} bytes)"
        )
        return output_path

    except Exception as e:
        logging.error(f"WeasyPrint conversion failed: {e}")
        raise


def convert_with_pypandoc(html_path: Path, output_path: Path) -> Path:
    """
    Convert HTML to PDF using pypandoc (fallback method).

    Args:
        html_path: Path to input HTML file
        output_path: Path for output PDF file

    Returns:
        Path to generated PDF file
    """
    if not PYPANDOC_AVAILABLE:
        raise ImportError("pypandoc is not installed. Run: pdm add pypandoc")

    logging.info(f"Converting with pypandoc: {html_path} → {output_path}")

    try:
        # Convert with pypandoc
        pypandoc.convert_file(
            str(html_path),
            "pdf",
            outputfile=str(output_path),
            extra_args=[
                "--pdf-engine=pdflatex",  # Use pdflatex engine (usually available)
                "--variable=geometry:a4paper",
                "--variable=geometry:margin=2cm",
                "--standalone",
                "--embed-resources",
            ],
        )

        # Verify PDF was created
        if not output_path.exists():
            # Try without pdflatex engine
            logging.warning("pdflatex engine failed, trying default engine")
            pypandoc.convert_file(
                str(html_path),
                "pdf",
                outputfile=str(output_path),
                extra_args=["--standalone", "--embed-resources"],
            )

        if not output_path.exists():
            raise RuntimeError("PDF file was not created")

        if output_path.stat().st_size == 0:
            raise RuntimeError("PDF file is empty")

        logging.info(
            f"Successfully created PDF: {output_path} ({output_path.stat().st_size:,} bytes)"
        )
        return output_path

    except Exception as e:
        logging.error(f"pypandoc conversion failed: {e}")
        raise


def convert_html_to_pdf(
    input_path: Path,
    output_path: Optional[Path] = None,
    prefer_weasyprint: bool = True,
    verbose: bool = False,
) -> Tuple[Path, str]:
    """
    Convert HTML file to PDF with automatic backend selection.

    Args:
        input_path: Path to input HTML file
        output_path: Optional path for output PDF (defaults to input with .pdf extension)
        prefer_weasyprint: Whether to prefer WeasyPrint over pypandoc
        verbose: Enable verbose logging

    Returns:
        Tuple of (PDF path, backend used)
    """
    setup_logging(verbose)

    # Validate input
    validate_html_file(input_path)

    # Determine output path
    if output_path is None:
        output_path = input_path.with_suffix(".pdf")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Try conversion with preferred backend
    backend_used = None

    if prefer_weasyprint and WEASYPRINT_AVAILABLE:
        try:
            result = convert_with_weasyprint(input_path, output_path)
            backend_used = "weasyprint"
            return result, backend_used
        except Exception as e:
            logging.warning(f"WeasyPrint failed, trying pypandoc: {e}")

    # Try pypandoc as fallback or primary
    if PYPANDOC_AVAILABLE:
        try:
            result = convert_with_pypandoc(input_path, output_path)
            backend_used = "pypandoc"
            return result, backend_used
        except Exception as e:
            logging.error(f"pypandoc also failed: {e}")

    # If we get here, no backend worked
    available = []
    if WEASYPRINT_AVAILABLE:
        available.append("weasyprint")
    if PYPANDOC_AVAILABLE:
        available.append("pypandoc")

    if not available:
        raise RuntimeError(
            "No PDF conversion backend available. Install weasyprint with: pdm add weasyprint"
        )
    else:
        raise RuntimeError(f"All available backends failed: {', '.join(available)}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Convert HTML files to PDF with CSS preservation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s report.html
  %(prog)s report.html -o output.pdf
  %(prog)s report.html --pypandoc --verbose
  %(prog)s report.html --check-backends

Note: WeasyPrint provides the best CSS support but requires installation:
  pdm add weasyprint
        """,
    )

    parser.add_argument("input", type=Path, nargs="?", help="Input HTML file path")

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output PDF file path (default: input file with .pdf extension)",
    )

    parser.add_argument("--pypandoc", action="store_true", help="Prefer pypandoc over weasyprint")

    parser.add_argument(
        "--check-backends", action="store_true", help="Check which backends are available and exit"
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Check backends if requested
    if args.check_backends:
        print("Available PDF conversion backends:")
        if WEASYPRINT_AVAILABLE:
            print("  ✅ WeasyPrint (recommended for CSS support)")
        else:
            print("  ❌ WeasyPrint (install with: pdm add weasyprint)")

        if PYPANDOC_AVAILABLE:
            print("  ✅ pypandoc (basic conversion)")
        else:
            print("  ❌ pypandoc (install with: pdm add pypandoc)")

        sys.exit(0)

    # Ensure input is provided for conversion
    if not args.input:
        parser.error("input file is required for conversion")

    try:
        pdf_path, backend = convert_html_to_pdf(
            input_path=args.input,
            output_path=args.output,
            prefer_weasyprint=not args.pypandoc,
            verbose=args.verbose,
        )

        print(f"✅ Successfully converted to PDF using {backend}: {pdf_path}")

        # Show file size
        size_kb = pdf_path.stat().st_size / 1024
        if size_kb < 1024:
            print(f"   File size: {size_kb:.1f} KB")
        else:
            print(f"   File size: {size_kb / 1024:.1f} MB")

    except Exception as e:
        print(f"❌ Conversion failed: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
