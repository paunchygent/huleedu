"""Configuration for the CLI."""

import os
from pathlib import Path

IDENTITY_BASE_URL = os.getenv("IDENTITY_BASE_URL", "http://localhost:7005/v1/auth")
CJ_ADMIN_BASE_URL = os.getenv("CJ_ADMIN_BASE_URL", "http://localhost:9095/admin/v1")
TOKEN_CACHE_PATH = Path(
    os.getenv("CJ_ADMIN_TOKEN_PATH", Path.home() / ".huleedu" / "cj_admin_token.json")
)
CJ_ADMIN_TOKEN_OVERRIDE = os.getenv("CJ_ADMIN_TOKEN")
CJ_ADMIN_EMAIL = os.getenv("CJ_ADMIN_EMAIL")
CJ_ADMIN_PASSWORD = os.getenv("CJ_ADMIN_PASSWORD")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
HULEEDU_ENVIRONMENT = os.getenv("HULEEDU_ENVIRONMENT", "development")
