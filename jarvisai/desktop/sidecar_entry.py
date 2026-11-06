"""PyInstaller entrypoint for the JARVIS desktop FastAPI sidecar."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _prepare_paths() -> None:
    # Frozen binary: keep working directory under user data when provided.
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        backend = meipass / "backend"
        if backend.is_dir() and str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        root = meipass
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    else:
        project = Path(__file__).resolve().parents[1]
        backend = project / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))


def main() -> None:
    _prepare_paths()
    parser = argparse.ArgumentParser(description="JARVIS desktop sidecar")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")))
    args = parser.parse_args()

    os.environ.setdefault("JARVIS_DESKTOP", "1")

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
        factory=False,
    )


if __name__ == "__main__":
    main()
