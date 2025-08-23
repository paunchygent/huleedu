"""Development routes for Email Service.

This module provides development and testing endpoints for email functionality.
These routes should only be available in development environments.
"""

from __future__ import annotations

from dishka import FromDishka
from quart import Blueprint, jsonify, request
from quart_dishka import inject

from services.email_service.config import Settings
from services.email_service.protocols import EmailProvider, TemplateRenderer

dev_bp = Blueprint("dev", __name__, url_prefix="/v1/emails/dev")


@dev_bp.post("/send")
@inject
async def send_dev_email(
    email_provider: FromDishka[EmailProvider],
    template_renderer: FromDishka[TemplateRenderer],
    settings: FromDishka[Settings],
):
    """Send a test email for development purposes.

    Only available in development mode.
    """
    if settings.is_production():
        return jsonify({"error": "Development endpoint not available in production"}), 403

    data = await request.get_json()

    required_fields = ["to", "template_id", "variables"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields", "required": required_fields}), 400

    try:
        # Render template
        rendered = await template_renderer.render(
            template_id=data["template_id"], variables=data["variables"]
        )

        # Send email
        result = await email_provider.send_email(
            to=data["to"],
            subject=rendered.subject,
            html_content=rendered.html_content,
            text_content=rendered.text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            from_name=settings.DEFAULT_FROM_NAME,
        )

        return jsonify(
            {
                "success": result.success,
                "provider_message_id": result.provider_message_id,
                "error_message": result.error_message,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500


@dev_bp.get("/templates")
@inject
async def list_templates(
    template_renderer: FromDishka[TemplateRenderer],
    settings: FromDishka[Settings],
):
    """List available email templates for development."""
    if settings.is_production():
        return jsonify({"error": "Development endpoint not available in production"}), 403

    # This would list available templates
    # For now return a placeholder response
    return jsonify({"templates": ["verification", "password_reset", "welcome", "notification"]})
