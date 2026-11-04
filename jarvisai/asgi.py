"""Vercel FastAPI entrypoint — exposes `app` with the same imports as local uvicorn."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.main import app as app  # noqa: E402
except Exception as exc:  # pragma: no cover - deploy diagnostics only
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    _error = f"{type(exc).__name__}: {exc}"
    _trace = traceback.format_exc()
    app = FastAPI(title="JARVIS API (boot error)")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def boot_error(full_path: str = ""):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "JARVIS backend failed to start.",
                "error": _error,
                "trace": _trace[-4000:],
                "path": full_path,
            },
        )
