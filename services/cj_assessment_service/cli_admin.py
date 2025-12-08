"""Typer-based admin helper for CJ assessment service (Deprecated Wrapper).

This file is a deprecated wrapper. The CLI has been refactored into the
`services.cj_assessment_service.cli` package. New commands should be added
to `services.cj_assessment_service.cli.main`.
"""

from services.cj_assessment_service.cli.main import app

if __name__ == "__main__":
    app()
