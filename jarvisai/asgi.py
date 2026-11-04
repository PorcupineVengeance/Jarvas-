"""Vercel FastAPI entrypoint — exposes `app` with the same imports as local uvicorn."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import app as app  # noqa: E402
