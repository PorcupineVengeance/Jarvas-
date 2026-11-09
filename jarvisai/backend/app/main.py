from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
import logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.chat import router as chat_router
from app.api.desktop import router as desktop_router
from app.api.files import router as files_router
from app.api.integrations import router as integrations_router
from app.api.memory import router as memory_router
from app.api.realtime import router as realtime_router
from app.api.reminders import router as reminders_router
from app.api.research import router as research_router
from app.api.system import router as system_router
from app.api.tasks import router as tasks_router
from app.api.voice import router as voice_router
from app.core.config import get_settings
from app.core.security import request_origin_is_trusted
from app.database.base import Base
from app.database.session import get_engine
from app.services.desktop_settings import apply_desktop_settings_on_boot
from app.services.file_manager import ensure_app_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("jarvis")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _frontend_dir() -> Path:
    return get_settings().frontend_dist


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        apply_desktop_settings_on_boot()
    except Exception:
        logger.exception("Desktop settings overlay failed; continuing with env defaults.")
    settings = get_settings()
    on_vercel = bool(__import__("os").getenv("VERCEL"))
    if not on_vercel:
        try:
            ensure_app_storage()
        except Exception:
            logger.exception("Storage init failed; continuing with limited file features.")
        for folder in ("data", "logs"):
            try:
                Path(folder).mkdir(exist_ok=True)
            except Exception:
                logger.warning("Could not create %s directory", folder)
    try:
        Base.metadata.create_all(bind=get_engine())
    except Exception:
        logger.exception("Database init failed; API may be degraded.")
    logger.info(
        "JARVIS ready | llm=%s research=%s stt=%s tts=%s local_auth=%s open_access=%s computer=%s desktop=%s vercel=%s",
        settings.llm_ready,
        settings.research_ready,
        settings.transcription_ready,
        settings.tts_ready,
        settings.local_auth_ready,
        settings.jarvis_open_access,
        settings.jarvis_enable_computer_control,
        settings.is_desktop,
        on_vercel,
    )
    yield
    try:
        from app.services.http_client import close_http_client
        await close_http_client()
    except Exception:
        logger.exception("HTTP client shutdown failed")


app = FastAPI(
    title="JARVIS API",
    version="1.1.0",
    description="A modular, permission-aware personal AI assistant API.",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}", "path": request.url.path},
    )


for router in (
    auth_router,
    chat_router,
    tasks_router,
    memory_router,
    reminders_router,
    system_router,
    voice_router,
    research_router,
    files_router,
    integrations_router,
    automation_router,
    desktop_router,
    realtime_router,
):
    app.include_router(router)

_rate_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    settings = get_settings()
    # Open access (and same-site Vercel rewrites) should not block browser POSTs.
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path.startswith("/api/")
        and not settings.jarvis_open_access
        and not request_origin_is_trusted(request)
    ):
        return JSONResponse(status_code=403, content={"detail": "Cross-origin state changes are not allowed."})
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/auth/session", "/api/auth/config"}:
        key = request.client.host if request.client else "unknown"
        now = monotonic()
        bucket = _rate_windows[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= 120:
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Pause briefly and retry."}, headers={"Retry-After": "10"})
        bucket.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "microphone=(self), camera=(self), geolocation=(self), display-capture=(self), "
        "accelerometer=(), gyroscope=(), magnetometer=(), payment=(), usb=()"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/manus-routes.json", include_in_schema=False)
def route_manifest():
    path = PROJECT_ROOT / "public" / "manus-routes.json"
    if not path.is_file():
        return JSONResponse(status_code=404, content={"detail": "Route manifest not found."})
    return FileResponse(path, media_type="application/json")


def _serve_frontend(path: str):
    frontend_dir = _frontend_dir()
    index = frontend_dir / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=503, content={"detail": "JARVIS frontend has not been built yet. Run: cd frontend && pnpm install && pnpm build"})
    if path:
        candidate = (frontend_dir / path).resolve()
        if frontend_dir.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(index)


@app.get("/", include_in_schema=False)
def root():
    # On Vercel the Vite service owns the UI; keep API root informative.
    if __import__("os").getenv("VERCEL"):
        return {"service": "jarvis-api", "status": "ok", "docs": "/docs"}
    return _serve_frontend("")


# Local/dev only: serve the built SPA. Never register this on Vercel — it steals
# GET /api/* and shows up as confusing 404s in the browser console.
if not __import__("os").getenv("VERCEL"):
    @app.get("/{path:path}", include_in_schema=False)
    def frontend_or_spa(path: str):
        if path == "api" or path.startswith(("api/", "manus-storage/", "__manus/", "__system__/")):
            return JSONResponse(status_code=404, content={"detail": "Not found."})
        return _serve_frontend(path)
