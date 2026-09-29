"""FastAPI application entry point."""

from pathlib import Path
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.requests import Request

from app.config import settings
from app.routes.auth import router as auth_router
from app.routes.rbac import router as rbac_router
from app.routes.summaries import router as summaries_router
from app.routes.transcripts import router as transcripts_router
from app.routes.upload_history import router as upload_history_router
from app.routes.videos import router as videos_router
from app.routes.key_moments import router as key_moments_router
from app.routes.mcqs import router as mcq_router
from app.routes.analytics import creator_router as creator_analytics_router
from app.routes.analytics import router as analytics_router

logger = logging.getLogger(__name__)
ALLOWED_FRONTEND_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

media_root = Path(settings.local_storage_path)
if not media_root.is_absolute():
    media_root = Path(__file__).resolve().parent.parent / media_root
media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_root)), name="media")


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    """Add proper CORS and media headers for cross-origin requests."""

    async def dispatch(self, request: Request, call_next):
        logger.info("API request method=%s path=%s", request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled API error method=%s path=%s", request.method, request.url.path)
            raise
        
        # Media needs to be embeddable by the configured frontend.
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        
        # Add cache headers for static media
        if "/media/" in request.url.path:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        
        return response


app.add_middleware(CORSHeaderMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(rbac_router)
app.include_router(videos_router)
app.include_router(upload_history_router)
app.include_router(transcripts_router)
app.include_router(summaries_router)
app.include_router(key_moments_router)
app.include_router(mcq_router)
app.include_router(analytics_router)
app.include_router(creator_analytics_router)


@app.exception_handler(Exception)
async def unhandled_api_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a CORS-compatible safe response for unexpected request failures."""

    logger.exception("Returning safe 500 method=%s path=%s", request.method, request.url.path, exc_info=exc)
    response = JSONResponse(status_code=500, content={"detail": "The backend could not complete this request."})
    origin = request.headers.get("origin")
    if origin in ALLOWED_FRONTEND_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.get("/", tags=["health"])
def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""

    return {"message": "ClipMind AI API is running"}
