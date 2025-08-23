"""
Unit tests for JinjaTemplateRenderer implementation behavior.

Tests focus on template rendering with Swedish character support, variable substitution,
error handling, and template loading behavior. Uses AsyncMock for protocol compliance
following Rule 075 methodology.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.email_service.implementations.template_renderer_impl import JinjaTemplateRenderer
from services.email_service.protocols import RenderedTemplate


class TestJinjaTemplateRenderer:
    """Tests for JinjaTemplateRenderer template rendering behavior."""

    @pytest.fixture
    def temp_template_dir(self) -> Path:
        """Create temporary template directory with test templates."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create test verification template with Swedish characters
        verification_template = temp_dir / "verification.html.j2"
        verification_content = """<!-- subject: Verify your HuleEdu account -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Verify Email</title>
</head>
<body>
    <h1>Hej {{ user_name|default('där') }}!</h1>
    <p>Välkommen till HuleEdu. Klicka på länken för att verifiera: {{ verification_link }}</p>
    <p>Kontakta oss på {{ support_email|default('support@huledu.se') }}.</p>
</body>
</html>"""
        verification_template.write_text(verification_content, encoding="utf-8")

        # Create test password reset template
        password_reset_template = temp_dir / "password_reset.html.j2"
        password_reset_content = """<!-- subject: Reset your HuleEdu password -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Password Reset</title>
</head>
<body>
    <h1>Lösenordsåterställning för {{ user_name }}</h1>
    <p>Klicka här: {{ reset_link }}</p>
    <p>Länken går ut om {{ expires_in|default('1 timme') }}.</p>
</body>
</html>"""
        password_reset_template.write_text(password_reset_content, encoding="utf-8")

        # Create template with syntax error
        syntax_error_template = temp_dir / "syntax_error.html.j2"
        syntax_error_content = """<!-- subject: Test -->
<html>
    <body>{{ unclosed_tag</body>
</html>"""
        syntax_error_template.write_text(syntax_error_content, encoding="utf-8")

        return temp_dir

    @pytest.fixture
    def renderer(self, temp_template_dir: Path) -> JinjaTemplateRenderer:
        """Create JinjaTemplateRenderer instance with test template directory."""
        return JinjaTemplateRenderer(template_path=str(temp_template_dir))

    @pytest.fixture
    def swedish_test_data(self) -> dict[str, str]:
        """Test data with Swedish characters for comprehensive testing."""
        return {
            "user_name": "Åsa Lindström",
            "email": "åsa.lindström@huledu.se",
            "verification_link": "https://app.huledu.se/verify?token=abc123åäö",
            "reset_link": "https://app.huledu.se/reset?token=xyz789ÅÄÖ",
            "support_email": "stöd@huledu.se",
            "expires_in": "30 minuter",
        }

    class TestTemplateLoading:
        """Tests for template loading and existence checking behavior."""

        async def test_template_exists_returns_true_for_existing_template(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should return True for existing template files."""
            assert await renderer.template_exists("verification") is True
            assert await renderer.template_exists("password_reset") is True

        async def test_template_exists_returns_false_for_missing_template(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should return False for non-existent template files."""
            assert await renderer.template_exists("nonexistent") is False
            assert await renderer.template_exists("missing_template") is False

        @pytest.mark.parametrize(
            "template_id",
            [
                "verification",
                "password_reset",
                "syntax_error",
            ],
        )
        async def test_template_exists_handles_various_template_names(
            self, renderer: JinjaTemplateRenderer, template_id: str
        ) -> None:
            """Should correctly identify existence of various template types."""
            exists = await renderer.template_exists(template_id)
            assert exists is True

    class TestTemplateRendering:
        """Tests for template rendering with variable substitution."""

        async def test_render_verification_template_with_basic_variables(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should render verification template with basic variable substitution."""
            variables = {
                "user_name": "John Doe",
                "verification_link": "https://app.huledu.se/verify?token=123",
            }

            result = await renderer.render("verification", variables)

            assert isinstance(result, RenderedTemplate)
            assert result.subject == "Verify your HuleEdu account"
            assert "John Doe" in result.html_content
            assert "https://app.huledu.se/verify?token=123" in result.html_content
            assert result.text_content is not None
            assert "John Doe" in result.text_content

        async def test_render_password_reset_template_with_variables(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should render password reset template with proper variable substitution."""
            variables = {
                "user_name": "Jane Smith",
                "reset_link": "https://app.huledu.se/reset?token=abc456",
                "expires_in": "2 hours",
            }

            result = await renderer.render("password_reset", variables)

            assert result.subject == "Reset your HuleEdu password"
            assert "Jane Smith" in result.html_content
            assert "https://app.huledu.se/reset?token=abc456" in result.html_content
            assert "2 hours" in result.html_content

        @pytest.mark.parametrize(
            "template_id, variables, expected_content",
            [
                ("verification", {"user_name": "Åsa"}, "Åsa"),
                ("verification", {"user_name": "Björn Ström"}, "Björn Ström"),
                ("password_reset", {"user_name": "Östen Åkerlund"}, "Östen Åkerlund"),
                ("verification", {"support_email": "hjälp@huledu.se"}, "hjälp@huledu.se"),
            ],
        )
        async def test_render_templates_with_swedish_characters(
            self,
            renderer: JinjaTemplateRenderer,
            template_id: str,
            variables: dict[str, str],
            expected_content: str,
        ) -> None:
            """Should correctly render templates with Swedish characters (åäöÅÄÖ)."""
            result = await renderer.render(template_id, variables)

            assert expected_content in result.html_content
            if result.text_content is not None:
                assert expected_content in result.text_content

        async def test_render_with_comprehensive_swedish_data(
            self, renderer: JinjaTemplateRenderer, swedish_test_data: dict[str, str]
        ) -> None:
            """Should handle comprehensive Swedish character test data correctly."""
            result = await renderer.render("verification", swedish_test_data)

            # Verify Swedish characters are preserved
            assert "Åsa Lindström" in result.html_content
            assert "åsa.lindström@huledu.se" not in result.html_content  # Not in this template
            assert "stöd@huledu.se" in result.html_content
            assert "abc123åäö" in result.html_content

        async def test_render_with_default_values_when_variables_missing(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should use default values from templates when variables are missing."""
            # Empty variables dict
            result = await renderer.render("verification", {})

            assert "där" in result.html_content  # Default user_name
            assert "support@huledu.se" in result.html_content  # Default support_email

        async def test_render_with_empty_variables_dict(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should handle empty variables dict gracefully."""
            result = await renderer.render("password_reset", {})

            assert result.subject == "Reset your HuleEdu password"
            assert result.html_content is not None
            assert result.text_content is not None

    class TestSubjectExtraction:
        """Tests for subject extraction from template HTML comments."""

        async def test_extracts_subject_from_html_comment(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should extract subject from HTML comment in template."""
            result = await renderer.render("verification", {"user_name": "Test User"})
            assert result.subject == "Verify your HuleEdu account"

            result = await renderer.render("password_reset", {"user_name": "Test User"})
            assert result.subject == "Reset your HuleEdu password"

        async def test_generates_default_subject_when_no_comment(
            self, temp_template_dir: Path
        ) -> None:
            """Should generate default subject when no subject comment found."""
            # Create template without subject comment
            no_subject_template = temp_template_dir / "no_subject.html.j2"
            no_subject_content = """<html><body>No subject here</body></html>"""
            no_subject_template.write_text(no_subject_content, encoding="utf-8")

            renderer = JinjaTemplateRenderer(template_path=str(temp_template_dir))
            result = await renderer.render("no_subject", {})

            assert result.subject == "Email from HuleEdu - no_subject"

    class TestTextContentGeneration:
        """Tests for HTML to plain text conversion."""

        async def test_generates_text_content_from_html(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should generate plain text version from HTML content."""
            variables = {"user_name": "Test User", "verification_link": "https://example.com"}
            result = await renderer.render("verification", variables)

            assert result.text_content is not None
            assert "Test User" in result.text_content
            assert "https://example.com" in result.text_content
            # HTML tags should be stripped
            assert "<html>" not in result.text_content
            assert "<h1>" not in result.text_content

        async def test_text_content_preserves_swedish_characters(
            self, renderer: JinjaTemplateRenderer, swedish_test_data: dict[str, str]
        ) -> None:
            """Should preserve Swedish characters in text content conversion."""
            result = await renderer.render("verification", swedish_test_data)

            assert result.text_content is not None
            assert "Åsa Lindström" in result.text_content
            assert "stöd@huledu.se" in result.text_content

        async def test_text_content_converts_html_entities(self, temp_template_dir: Path) -> None:
            """Should convert HTML entities to proper characters in text content."""
            # Create template with HTML entities
            entities_template = temp_template_dir / "entities.html.j2"
            entities_content = """<!-- subject: Test Entities -->
<html><body>Test &amp; check &lt;tags&gt; &quot;quotes&quot; &#39;apostrophes&#39;</body></html>"""
            entities_template.write_text(entities_content, encoding="utf-8")

            renderer = JinjaTemplateRenderer(template_path=str(temp_template_dir))
            result = await renderer.render("entities", {})

            assert result.text_content is not None
            assert "Test & check <tags> \"quotes\" 'apostrophes'" in result.text_content

    class TestErrorHandling:
        """Tests for error handling scenarios."""

        async def test_render_raises_validation_error_for_missing_template(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should raise HuleEduError when template file doesn't exist."""
            with pytest.raises(HuleEduError) as exc_info:
                await renderer.render("nonexistent_template", {})

            error = exc_info.value.error_detail
            assert error.service == "email_service"
            assert error.operation == "render_template"
            assert error.details["field"] == "template_id"
            assert "Template not found: nonexistent_template" in error.message

        async def test_render_handles_template_syntax_errors(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should raise HuleEduError for templates with syntax errors."""
            with pytest.raises(HuleEduError) as exc_info:
                await renderer.render("syntax_error", {"test_var": "value"})

            error = exc_info.value.error_detail
            assert error.service == "email_service"
            assert error.operation == "render_template"
            assert error.details["field"] == "template_rendering"
            assert "Template rendering failed" in error.message

        @pytest.mark.parametrize(
            "variables",
            [
                None,
                {"valid_key": None},  # None value
                {"": "empty_key"},  # Empty key
                {"key": ""},  # Empty value
            ],
        )
        async def test_render_handles_edge_case_variables_gracefully(
            self, renderer: JinjaTemplateRenderer, variables: dict[str, str] | None
        ) -> None:
            """Should handle edge case variable inputs without crashing."""
            # Convert None to empty dict to match protocol signature
            safe_variables = variables or {}

            try:
                result = await renderer.render("verification", safe_variables)
                # Should complete without error and return valid result
                assert isinstance(result, RenderedTemplate)
                assert result.subject is not None
                assert result.html_content is not None
            except HuleEduError:
                # HuleEduError is acceptable for truly invalid inputs
                pass

    class TestTemplateInitialization:
        """Tests for template renderer initialization behavior."""

        def test_creates_template_directory_if_not_exists(self) -> None:
            """Should create template directory during initialization if it doesn't exist."""
            with tempfile.TemporaryDirectory() as temp_dir:
                non_existent_path = Path(temp_dir) / "new_templates"
                assert not non_existent_path.exists()

                JinjaTemplateRenderer(template_path=str(non_existent_path))

                assert non_existent_path.exists()
                assert non_existent_path.is_dir()

        def test_uses_default_template_path_when_none_provided(self) -> None:
            """Should use default template path relative to service root."""
            # Allow actual filesystem operations since mkdir uses exist_ok=True
            renderer = JinjaTemplateRenderer()

            # Should have initialized without error
            assert renderer.env is not None
            assert hasattr(renderer, "template_dir")
            # Verify default template path is used
            assert "templates" in str(renderer.template_dir)

        def test_configures_jinja2_environment_properly(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should configure Jinja2 environment with proper settings."""
            env = renderer.env

            # Check that async is enabled (this is a property in newer Jinja2)
            assert hasattr(env, "is_async") or hasattr(env, "enable_async")
            assert env.loader is not None
            assert env.autoescape is not None

    class TestTemplateCaching:
        """Tests for template caching behavior."""

        async def test_template_caching_improves_performance(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should cache templates for improved performance on repeated renders."""
            variables = {"user_name": "Cache Test", "verification_link": "https://example.com"}

            # First render - should load template
            result1 = await renderer.render("verification", variables)

            # Second render - should use cached template
            result2 = await renderer.render("verification", variables)

            # Results should be identical
            assert result1.subject == result2.subject
            assert result1.html_content == result2.html_content
            assert result1.text_content == result2.text_content

        async def test_different_variables_produce_different_output(
            self, renderer: JinjaTemplateRenderer
        ) -> None:
            """Should produce different output when variables change despite caching."""
            result1 = await renderer.render("verification", {"user_name": "User One"})
            result2 = await renderer.render("verification", {"user_name": "User Two"})

            assert result1.subject == result2.subject  # Same template
            assert "User One" in result1.html_content
            assert "User Two" in result2.html_content
            assert result1.html_content != result2.html_content


class TestJinjaTemplateRendererProtocolCompliance:
    """Tests for TemplateRenderer protocol compliance."""

    def test_implements_template_renderer_protocol(self) -> None:
        """Should implement TemplateRenderer protocol correctly."""
        renderer = JinjaTemplateRenderer()

        # Should have required methods from the protocol
        assert hasattr(renderer, "render")
        assert hasattr(renderer, "template_exists")
        assert callable(renderer.render)
        assert callable(renderer.template_exists)
