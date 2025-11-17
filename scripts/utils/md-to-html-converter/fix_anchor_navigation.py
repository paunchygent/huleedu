#!/usr/bin/env python3
"""
Post-processor to fix anchor navigation issues in generated HTML.
Adds JavaScript to handle smooth scrolling and prevent content disappearing.
"""

import sys
from pathlib import Path


def fix_anchor_navigation(html_file_path: str) -> str:
    """
    Fix anchor navigation issues by adding JavaScript for smooth scrolling.

    Args:
        html_file_path: Path to the HTML file to fix

    Returns:
        Path to the fixed HTML file
    """
    html_path = Path(html_file_path)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file_path}")

    # Read the HTML content
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # JavaScript to fix anchor navigation
    anchor_fix_script = """
    <script>
        // Fix anchor navigation to prevent content from disappearing
        document.addEventListener('DOMContentLoaded', function() {
            // Find all TOC links
            const tocLinks = document.querySelectorAll('.toc-nav a[href^="#"]');

            tocLinks.forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault(); // Prevent default anchor behavior

                    const targetId = this.getAttribute('href').substring(1);
                    const targetElement = document.getElementById(targetId);

                    if (targetElement) {
                        // Smooth scroll to target with offset for navigation
                        const offsetTop = targetElement.offsetTop - 20; // 20px offset

                        window.scrollTo({
                            top: offsetTop,
                            behavior: 'smooth'
                        });

                        // Update URL without triggering default behavior
                        history.pushState(null, null, '#' + targetId);

                        // Optional: Highlight the target briefly
                        targetElement.style.transition = 'background-color 0.3s ease';
                        targetElement.style.backgroundColor = '#fff3cd';
                        setTimeout(() => {
                            targetElement.style.backgroundColor = '';
                        }, 1000);
                    }
                });
            });

            // Handle direct URL hash navigation (e.g., page reload with #anchor)
            if (window.location.hash) {
                setTimeout(() => {
                    const targetId = window.location.hash.substring(1);
                    const targetElement = document.getElementById(targetId);
                    if (targetElement) {
                        const offsetTop = targetElement.offsetTop - 20;
                        window.scrollTo({
                            top: offsetTop,
                            behavior: 'smooth'
                        });
                    }
                }, 100); // Small delay to ensure page is loaded
            }
        });
    </script>"""

    # Insert the script before the closing </body> tag
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", f"{anchor_fix_script}\n</body>")
    else:
        # Fallback: add before closing </html>
        html_content = html_content.replace("</html>", f"{anchor_fix_script}\n</html>")

    # Create output filename
    output_path = html_path.parent / f"{html_path.stem}_fixed{html_path.suffix}"

    # Write the fixed HTML
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Fixed anchor navigation in: {output_path}")
    return str(output_path)


def main():
    """Main function to handle command line usage."""
    if len(sys.argv) != 2:
        print("Usage: python fix_anchor_navigation.py <html_file>")
        print("\nThis script fixes anchor navigation issues by adding JavaScript")
        print("to handle smooth scrolling and prevent content from disappearing.")
        sys.exit(1)

    html_file = sys.argv[1]

    try:
        fixed_file = fix_anchor_navigation(html_file)
        print(f"Successfully fixed {html_file}")
        print(f"Fixed version saved as: {fixed_file}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
