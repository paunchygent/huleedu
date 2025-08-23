"""Jinja2 template renderer implementation for Email Service.

This module provides a flexible template renderer that can handle any email template
with variable substitution, subject extraction, and text content generation.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

# Basic text conversion without external dependencies
from huleedu_service_libs.error_handling import raise_validation_error
from huleedu_service_libs.logging_utils import create_service_logger
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from services.email_service.protocols import RenderedTemplate, TemplateRenderer

logger = create_service_logger("email_service.template_renderer")


class JinjaTemplateRenderer(TemplateRenderer):
    """Jinja2-based template renderer for flexible email template processing.

    Supports:
    - Async template rendering
    - Subject extraction from HTML comments
    - Variable substitution with any template
    - Text content generation from HTML
    - Template existence validation
    """

    def __init__(self, template_path: str = "templates") -> None:
        """Initialize the Jinja2 template renderer.

        Args:
            template_path: Relative path to templates directory from service root
        """
        # Get template directory relative to service root
        service_root = Path(__file__).parent.parent
        self.template_dir = service_root / template_path

        logger.info(f"Initializing Jinja2 renderer with template directory: {self.template_dir}")

        # Create templates directory if it doesn't exist
        self.template_dir.mkdir(parents=True, exist_ok=True)

        # Configure Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,  # Enable async template rendering
        )

    async def render(
        self,
        template_id: str,
        variables: dict[str, str],
    ) -> RenderedTemplate:
        """Render an email template with variables.

        Args:
            template_id: Template identifier (without .html.j2 extension)
            variables: Variables to substitute in the template

        Returns:
            RenderedTemplate with subject, HTML content, and text content

        Raises:
            ValidationError: If template doesn't exist or rendering fails
        """
        template_filename = f"{template_id}.html.j2"

        logger.debug(
            f"Rendering template: {template_filename} with variables: {list(variables.keys())}"
        )

        try:
            # Load and render template
            template = self.env.get_template(template_filename)
            html_content = await template.render_async(**variables)

            # Extract subject from HTML comment
            subject = self._extract_subject(html_content)
            if not subject:
                logger.warning(f"No subject found in template {template_filename}, using default")
                subject = f"Email from HuleEdu - {template_id}"

            # Generate text content from HTML
            text_content = self._generate_text_content(html_content)

            logger.debug(f"Successfully rendered template {template_filename}")
            return RenderedTemplate(
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )

        except TemplateNotFound:
            logger.error(f"Template not found: {template_filename}")
            raise_validation_error(
                service="email_service",
                operation="render_template",
                field="template_id",
                message=f"Template not found: {template_id}",
                correlation_id=uuid4(),
            )
        except Exception as e:
            logger.error(f"Error rendering template {template_filename}: {e}", exc_info=True)
            raise_validation_error(
                service="email_service",
                operation="render_template",
                field="template_rendering",
                message=f"Template rendering failed: {e}",
                correlation_id=uuid4(),
            )

    async def template_exists(self, template_id: str) -> bool:
        """Check if a template exists.

        Args:
            template_id: Template identifier to check

        Returns:
            True if template exists, False otherwise
        """
        template_path = self.template_dir / f"{template_id}.html.j2"
        exists = template_path.exists()

        logger.debug(f"Template existence check for {template_id}: {exists}")
        return exists

    def _extract_subject(self, html_content: str) -> str | None:
        """Extract subject from HTML comment in template.

        Looks for: <!-- subject: Your Subject Here -->

        Args:
            html_content: Rendered HTML content

        Returns:
            Extracted subject or None if not found
        """
        # Look for subject in HTML comment
        subject_pattern = r"<!--\s*subject:\s*([^-]+?)\s*-->"
        match = re.search(subject_pattern, html_content, re.IGNORECASE | re.MULTILINE)

        if match:
            subject = match.group(1).strip()
            logger.debug(f"Extracted subject: {subject}")
            return subject

        return None

    def _generate_text_content(self, html_content: str) -> str:
        """Generate plain text content from HTML using basic conversion.

        Args:
            html_content: HTML content to convert

        Returns:
            Plain text version of the email
        """
        try:
            # Basic HTML to text conversion
            text_content = html_content

            # Convert common HTML elements to text equivalents
            text_content = re.sub(r"<br\s*/?>", "\n", text_content, flags=re.IGNORECASE)
            text_content = re.sub(r"<p[^>]*>", "\n", text_content, flags=re.IGNORECASE)
            text_content = re.sub(r"</p>", "\n", text_content, flags=re.IGNORECASE)
            text_content = re.sub(r"<div[^>]*>", "\n", text_content, flags=re.IGNORECASE)
            text_content = re.sub(r"</div>", "\n", text_content, flags=re.IGNORECASE)

            # Remove all other HTML tags
            text_content = re.sub(r"<[^>]+>", "", text_content)

            # Decode HTML entities
            text_content = text_content.replace("&nbsp;", " ")
            text_content = text_content.replace("&amp;", "&")
            text_content = text_content.replace("&lt;", "<")
            text_content = text_content.replace("&gt;", ">")
            text_content = text_content.replace("&quot;", '"')
            text_content = text_content.replace("&#39;", "'")

            # Clean up whitespace
            text_content = re.sub(r"\n\s*\n\s*\n", "\n\n", text_content)
            text_content = re.sub(r"[ \t]+", " ", text_content)
            text_content = text_content.strip()

            return text_content

        except Exception as e:
            logger.warning(f"Failed to generate text content: {e}")
            # Ultimate fallback: just remove tags
            text_content = re.sub(r"<[^>]+>", "", html_content)
            text_content = re.sub(r"\s+", " ", text_content)
            return text_content.strip()
