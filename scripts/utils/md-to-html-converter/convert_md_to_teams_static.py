#!/usr/bin/env python3
"""
Teams-compatible Markdown to HTML converter with static Mermaid images.
Converts Mermaid diagrams to PNG images for Teams chat compatibility.
"""

import base64
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple


def extract_mermaid_blocks(markdown_content: str) -> List[Tuple[str, str]]:
    """
    Extract Mermaid code blocks from markdown content.

    Returns:
        List of tuples (mermaid_code, placeholder_id)
    """
    mermaid_blocks = []
    pattern = r'```mermaid\n(.*?)\n```'
    matches = re.finditer(pattern, markdown_content, re.DOTALL)

    for i, match in enumerate(matches):
        mermaid_code = match.group(1).strip()
        placeholder_id = f"MERMAID_PLACEHOLDER_{i}"
        mermaid_blocks.append((mermaid_code, placeholder_id))

    return mermaid_blocks


def convert_mermaid_to_png(mermaid_code: str) -> Optional[str]:
    """
    Convert Mermaid code to PNG image using mermaid-cli.

    Returns:
        Base64 encoded PNG image or None if conversion fails
    """
    try:
        # Check if mermaid-cli is available
        subprocess.run(['mmdc', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: mermaid-cli (mmdc) not found. Install with: npm install -g @mermaid-js/mermaid-cli")
        return None

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as mmd_file:
            mmd_file.write(mermaid_code)
            mmd_file.flush()

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as png_file:
                # Convert Mermaid to PNG using mermaid-cli
                cmd = [
                    'mmdc',
                    '-i', mmd_file.name,
                    '-o', png_file.name,
                    '-t', 'default',
                    '-b', 'white',
                    '--width', '1200',
                    '--height', '800'
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    # Read the PNG file and encode as base64
                    with open(png_file.name, 'rb') as f:
                        png_data = f.read()
                        base64_image = base64.b64encode(png_data).decode('utf-8')
                        return base64_image
                else:
                    print(f"Error converting Mermaid: {result.stderr}")
                    return None

    except Exception as e:
        print(f"Error in Mermaid conversion: {e}")
        return None
    finally:
        # Cleanup temp files
        try:
            Path(mmd_file.name).unlink(missing_ok=True)
            Path(png_file.name).unlink(missing_ok=True)
        except:
            pass


def convert_markdown_to_teams_static(markdown_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert markdown file to Teams-compatible HTML with static Mermaid images.

    Args:
        markdown_path: Path to the markdown file
        output_path: Optional output path, defaults to same name with .html extension

    Returns:
        Path to the generated HTML file
    """
    markdown_file = Path(markdown_path)
    if not markdown_file.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    if output_path is None:
        output_path = str(markdown_file.with_suffix('.html'))

    # Read markdown content
    with open(markdown_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    # Extract Mermaid blocks
    mermaid_blocks = extract_mermaid_blocks(markdown_content)

    # Replace Mermaid blocks with placeholders
    modified_markdown = markdown_content
    for mermaid_code, placeholder_id in mermaid_blocks:
        pattern = r'```mermaid\n' + re.escape(mermaid_code) + r'\n```'
        modified_markdown = re.sub(pattern, f"<!-- {placeholder_id} -->", modified_markdown, count=1)

    # Teams-optimized HTML template
    html_template = """<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{title}</title>

    <!-- Teams-optimized styles -->
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: #ffffff;
            color: #323130;
            line-height: 1.6;
            scroll-behavior: smooth; /* Add smooth scrolling */
        }}

        /* Add scroll padding to account for fixed navigation */
        html {{
            scroll-padding-top: 80px; /* Offset for potential fixed elements */
        }}

        /* Teams chat compatibility */
        .teams-container {{
            background: #ffffff;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: #323130;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            line-height: 1.2;
        }}

        h1 {{
            border-bottom: 2px solid #0078d4;
            padding-bottom: 8px;
        }}

        /* Mermaid diagram as static image */
        .mermaid-image {{
            margin: 20px 0;
            text-align: center;
            background: #fafafa;
            border: 1px solid #e1dfdd;
            border-radius: 4px;
            padding: 16px;
        }}

        .mermaid-image img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}

        /* Code blocks */
        pre {{
            background-color: #f3f2f1;
            border: 1px solid #e1dfdd;
            border-radius: 4px;
            padding: 16px;
            overflow-x: auto;
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
        }}

        code {{
            background-color: #f3f2f1;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 0.9em;
        }}

        /* Tables - Teams style */
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}

        th, td {{
            border: 1px solid #e1dfdd;
            padding: 8px 12px;
            text-align: left;
        }}

        th {{
            background-color: #f3f2f1;
            font-weight: 600;
        }}

        /* Links - Teams blue */
        a {{
            color: #0078d4;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        /* Lists */
        ul, ol {{
            padding-left: 24px;
        }}

        li {{
            margin-bottom: 4px;
        }}

        /* Blockquotes */
        blockquote {{
            border-left: 4px solid #0078d4;
            margin: 16px 0;
            padding: 8px 16px;
            background-color: #f3f2f1;
            font-style: italic;
        }}

        /* Two-column layout */
        .wrapper-container {{
            display: flex;
            max-width: 100%;
            margin: 0;
            min-height: 100vh;
        }}

        .toc-nav {{
            width: 250px;
            min-width: 250px;
            background-color: #f5f5f5;
            border-right: 1px solid #d4d4d4;
            padding: 20px;
            box-sizing: border-box;
            position: sticky;
            top: 0;
            height: 100vh;
            overflow-y: auto;
        }}

        .main-content {{
            flex: 1;
            padding: 20px 40px;
            overflow-x: hidden;
            box-sizing: border-box;
        }}

        /* Fix anchor scroll offset to account for any fixed elements */
        .main-content h1, .main-content h2, .main-content h3, 
        .main-content h4, .main-content h5, .main-content h6 {{
            scroll-margin-top: 20px; /* Offset for smooth scrolling */
        }}

        /* Alternative approach using CSS scroll-snap for better anchor behavior */
        html {{
            scroll-behavior: smooth;
        }}

        /* TOC specific styles */
        .toc-nav ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}

        .toc-nav li {{
            margin-bottom: 5px;
        }}

        .toc-nav a {{
            display: block;
            padding: 8px 12px;
            border-radius: 4px;
            color: #323130;
            text-decoration: none;
            font-weight: normal; /* Ensure not bold by default */
            transition: background-color 0.2s ease; /* Smooth hover effect */
        }}

        .toc-nav a:hover {{
            background-color: #f3f2f1;
            text-decoration: none;
        }}

        .toc-nav a:active, .toc-nav a:focus {{
            background-color: #e1dfdd;
            outline: 2px solid #0078d4;
            outline-offset: 2px;
        }}

        /* Improve hierarchy visualization */
        .toc-nav ul ul {{
            padding-left: 15px;
            border-left: 2px solid #f3f2f1;
            margin-left: 8px;
        }}

        .toc-nav ul ul ul {{
            padding-left: 15px;
            border-left: 2px solid #e1dfdd;
        }}

        /* Responsive adjustments */
        @media (max-width: 768px) {{
            body {{
                padding: 10px; /* Reduce padding on mobile */
            }}

            .wrapper-container {{
                flex-direction: column;
                min-height: auto; /* Remove height constraint on mobile */
            }}

            .toc-nav {{
                position: static; /* Not fixed on mobile */
                flex: none;
                width: 100%;
                height: auto;
                max-height: 200px; /* Limit height on mobile */
                border-right: none;
                border-bottom: 1px solid #e1dfdd;
                padding-right: 0;
                padding-left: 0;
                padding-bottom: 20px;
                margin-bottom: 20px;
                overflow-y: auto;
                z-index: auto;
            }}

            .main-content {{
                margin-left: 0; /* Remove left margin on mobile */
                padding-top: 0;
            }}
        }}

        /* Improve scrollbar styling for modern browsers */
        .toc-nav::-webkit-scrollbar {{
            width: 6px;
        }}

        .toc-nav::-webkit-scrollbar-track {{
            background: #f3f2f1;
            border-radius: 3px;
        }}

        .toc-nav::-webkit-scrollbar-thumb {{
            background: #c8c6c4;
            border-radius: 3px;
        }}

        .toc-nav::-webkit-scrollbar-thumb:hover {{
            background: #a19f9d;
        }}

        .main-content::-webkit-scrollbar {{
            width: 8px;
        }}

        .main-content::-webkit-scrollbar-track {{
            background: #f3f2f1;
            border-radius: 4px;
        }}

        .main-content::-webkit-scrollbar-thumb {{
            background: #c8c6c4;
            border-radius: 4px;
        }}

        .main-content::-webkit-scrollbar-thumb:hover {{
            background: #a19f9d;
        }}

        /* Print styles */
        @media print {{
            body {{
                max-width: none;
                margin: 0;
                padding: 10mm;
            }}

            .mermaid-image {{
                break-inside: avoid;
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="teams-container">
        <div class="wrapper-container">
            <main class="main-content">
                {content}
            </main>
        </div>
    </div>
</body>
</html>"""

    try:
        # Convert markdown to HTML using pypandoc
        import pypandoc

        # Get document title from filename
        doc_title = Path(markdown_path).stem.replace('_', ' ').title()

        # Convert modified markdown to HTML
        pandoc_output = pypandoc.convert_text(
            modified_markdown,
            'html',
            format='markdown',
            extra_args=[
                '--no-highlight',
                '--wrap=none',
                '--standalone'
            ]
        )

        # Extract TOC from pandoc_output
        # Pandoc generates a <nav id="TOC" role="doc-toc"> element for the table of contents.
        toc_pattern = re.compile(r'<nav id="TOC"[^>]*>.*?</nav>', re.DOTALL)
        toc_match = toc_pattern.search(pandoc_output)
        toc_html = ""
        if toc_match:
            toc_html = toc_match.group(0)
            # Remove TOC from the main content to avoid duplication
            pandoc_output = toc_pattern.sub('', pandoc_output)

        # Extract only the body content from Pandoc's standalone output
        # to avoid CSS/JS conflicts with anchor navigation
        body_pattern = re.compile(r'<body[^>]*>(.*?)</body>', re.DOTALL)
        body_match = body_pattern.search(pandoc_output)
        if body_match:
            pandoc_output = body_match.group(1).strip()

        # Prepare the final HTML with the extracted TOC and main content
        final_html = html_template.format(
            title=doc_title,
            content=pandoc_output,
            toc_nav_content=toc_html
        )

        # Replace placeholders with Mermaid images
        for mermaid_code, placeholder_id in mermaid_blocks:
            png_base64 = convert_mermaid_to_png(mermaid_code)
            if png_base64:
                img_tag = f"<div class=\"mermaid-image\"><img src=\"data:image/png;base64,{png_base64}\" alt=\"Mermaid Diagram\"></div>"
                final_html = final_html.replace(f"<!-- {placeholder_id} -->", img_tag)

        # Write the final HTML to the output file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_html)

        logging.info(f"Successfully converted {markdown_path} to {output_path}")
        logging.info("Optimized for Microsoft Teams with static Mermaid images")
        return final_html

    except ImportError:
        print("Error: pypandoc is required. Install with: pip install pypandoc")
        sys.exit(1)
    except Exception as e:
        print(f"Error converting {markdown_path}: {e}")
        sys.exit(1)


def main():
    """Main function to handle command line usage."""
    if len(sys.argv) != 2:
        print("Usage: python convert_md_to_teams_static.py <markdown_file>")
        print("\nRequirements:")
        print("1. pip install pypandoc")
        print("2. npm install -g @mermaid-js/mermaid-cli")
        sys.exit(1)

    markdown_file = sys.argv[1]

    try:
        output_file = convert_markdown_to_teams_static(markdown_file)
        print(f"Successfully converted {markdown_file} to {output_file}")
        print("Optimized for Microsoft Teams with static Mermaid images")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
