"""Health and utility routes for BFF Teacher Service."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from services.bff_teacher_service.config import settings

router = APIRouter()


@router.get("/healthz", tags=["Health"])
async def health_check() -> dict[str, str | dict]:
    """Health check endpoint following Rule 072 format."""
    static_dir_exists = settings.STATIC_DIR.exists()
    index_exists = (settings.STATIC_DIR / "index.html").exists()
    assets_dir_exists = (settings.STATIC_DIR / "assets").exists()

    checks = {
        "static_dir_exists": static_dir_exists,
        "index_exists": index_exists,
        "assets_dir_exists": assets_dir_exists,
    }

    # Service is healthy if frontend is built, degraded if missing
    all_checks_pass = all(checks.values())
    overall_status = "healthy" if all_checks_pass else "degraded"

    return {
        "service": "bff_teacher_service",
        "status": overall_status,
        "message": f"BFF Teacher Service is {overall_status}",
        "version": "0.1.0",
        "checks": checks,
        "dependencies": {
            "frontend_build": {
                "status": "available" if index_exists else "missing",
                "note": "Run 'pdm run fe-build' to build frontend"
                if not index_exists
                else "Frontend assets ready",
            }
        },
    }


@router.get("/favicon.svg", include_in_schema=False, response_model=None)
async def favicon() -> FileResponse | JSONResponse:
    """Serve favicon."""
    favicon_path = settings.STATIC_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return JSONResponse(status_code=404, content={"detail": "Favicon not found"})
