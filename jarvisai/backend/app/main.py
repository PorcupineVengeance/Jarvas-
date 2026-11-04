from collections import defaultdict, deque
from pathlib import Path
from time import monotonic
import logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.integrations import router as integrations_router
from app.api.memory import router as memory_router
from app.api.realtime import router as realtime_router
from app.api.research import router as research_router
from app.api.system import router as system_router
from app.api.tasks import router as tasks_router
from app.api.voice import router as voice_router
from app.core.security import request_origin_is_trusted

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("jarvis")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"

app = FastAPI(title="JARVIS API", version="1.0.0", description="A modular, permission-aware personal AI assistant API.", docs_url="/docs", redoc_url=None)
for router in (auth_router, chat_router, tasks_router, memory_router, system_router, voice_router, research_router, files_router, integrations_router, automation_router, realtime_router):
    app.include_router(router)

_rate_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/") and not request_origin_is_trusted(request):
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
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=(), payment=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/manus-routes.json", include_in_schema=False)
def route_manifest():
    path = PROJECT_ROOT / "public" / "manus-routes.json"
    if not path.is_file():
        return JSONResponse(status_code=404, content={"detail": "Route manifest not found."})
    return FileResponse(path, media_type="application/json")


def _serve_frontend(path: str):
    index = FRONTEND_DIR / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=503, content={"detail": "JARVIS frontend has not been built yet."})
    if path:
        candidate = (FRONTEND_DIR / path).resolve()
        if FRONTEND_DIR.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
    return FileResponse(index)


@app.get("/", include_in_schema=False)
def root():
    return _serve_frontend("")


@app.get("/{path:path}", include_in_schema=False)
def frontend_or_spa(path: str):
    if path == "api" or path.startswith(("api/", "manus-storage/", "__manus/", "__system__/")):
        return JSONResponse(status_code=404, content={"detail": "Not found."})
    return _serve_frontend(path)
