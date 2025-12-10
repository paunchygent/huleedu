"""SPA fallback routes for BFF Teacher Service."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from services.bff_teacher_service.config import settings

router = APIRouter()


@router.get("/{_full_path:path}", include_in_schema=False, response_model=None)
async def serve_spa(_full_path: str) -> FileResponse | JSONResponse:
    """Serve SPA index.html for client-side routing.

    This catch-all route serves index.html for any unmatched path,
    enabling Vue Router's history mode for client-side navigation.

    Args:
        _full_path: The requested path (unused - all paths serve index.html).
    """
    index_path = settings.STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Frontend not built. Run: pdm run fe-build",
            "static_dir": str(settings.STATIC_DIR),
        },
    )
