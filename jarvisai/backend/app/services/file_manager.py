import shutil
from pathlib import Path
from app.core.config import get_settings
from app.core.permissions import path_is_allowed


class FileManagerError(RuntimeError):
    pass


def _ensure_allowed(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not path_is_allowed(resolved):
        raise FileManagerError(f"Path is outside authorized directories: {resolved}")
    return resolved


def list_directory(path: str) -> dict:
    target = _ensure_allowed(Path(path))
    if not target.exists():
        raise FileManagerError("Directory does not exist.")
    if not target.is_dir():
        raise FileManagerError("Path is not a directory.")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:500]:
        entries.append({"name": child.name, "path": str(child), "type": "dir" if child.is_dir() else "file", "size": child.stat().st_size if child.is_file() else None})
    return {"path": str(target), "entries": entries}


def find_files(directory: str, pattern: str) -> dict:
    root = _ensure_allowed(Path(directory))
    if not root.is_dir():
        raise FileManagerError("Search root must be a directory.")
    matches = []
    for path in root.rglob(pattern):
        if len(matches) >= 100:
            break
        if not path_is_allowed(path):
            continue
        matches.append({"name": path.name, "path": str(path), "size": path.stat().st_size if path.is_file() else None})
    return {"directory": str(root), "pattern": pattern, "matches": matches}


def create_folder(path: str) -> dict:
    target = _ensure_allowed(Path(path))
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "created": True}


def create_text_file(path: str, content: str) -> dict:
    target = _ensure_allowed(Path(path))
    if target.exists():
        raise FileManagerError("File already exists.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target), "bytes": len(content.encode("utf-8"))}


def read_text_file(path: str, max_chars: int = 40_000) -> dict:
    target = _ensure_allowed(Path(path))
    if not target.is_file():
        raise FileManagerError("File not found.")
    text = target.read_text(encoding="utf-8", errors="replace")[:max_chars]
    return {"path": str(target), "content": text, "truncated": len(text) >= max_chars}


def rename_path(source: str, destination: str) -> dict:
    src = _ensure_allowed(Path(source))
    dst = _ensure_allowed(Path(destination))
    if not src.exists():
        raise FileManagerError("Source path does not exist.")
    src.rename(dst)
    return {"from": str(src), "to": str(dst)}


def delete_path(path: str) -> dict:
    target = _ensure_allowed(Path(path))
    if not target.exists():
        raise FileManagerError("Path does not exist.")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"path": str(target), "deleted": True}


def ensure_app_storage() -> Path:
    root = get_settings().storage_path
    root.mkdir(parents=True, exist_ok=True)
    (root / "uploads").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    return root
