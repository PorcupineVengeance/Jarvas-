import platform
import subprocess
import webbrowser
from pathlib import Path
from app.core.config import get_settings
from app.core.permissions import computer_control_enabled, path_is_allowed


class ComputerControlError(RuntimeError):
    pass


def _require_enabled() -> None:
    if not computer_control_enabled():
        raise ComputerControlError("Computer control is disabled. Set JARVIS_ENABLE_COMPUTER_CONTROL=true for local automation.")


def open_application(name: str) -> dict:
    _require_enabled()
    app = name.strip()
    if not app or len(app) > 120 or any(ch in app for ch in ";|&`$"):
        raise ComputerControlError("Application name is invalid.")
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", "-a", app], check=True, timeout=15)
        elif system == "Windows":
            subprocess.run(["cmd", "/c", "start", "", app], check=True, timeout=15, shell=False)
        else:
            subprocess.run([app], check=True, timeout=15)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ComputerControlError(f"Could not open application '{app}'.") from exc
    return {"action": "open_application", "application": app, "status": "ok"}


def open_url(url: str) -> dict:
    _require_enabled()
    target = url.strip()
    if not target.startswith(("http://", "https://")) or len(target) > 2_000:
        raise ComputerControlError("Only http(s) URLs are allowed.")
    opened = webbrowser.open(target)
    return {"action": "open_url", "url": target, "status": "ok" if opened else "attempted"}


def open_path(path: str) -> dict:
    _require_enabled()
    target = Path(path).expanduser().resolve()
    if not path_is_allowed(target):
        raise ComputerControlError("Path is outside authorized directories.")
    if not target.exists():
        raise ComputerControlError("Path does not exist.")
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(target)], check=True, timeout=15)
        elif system == "Windows":
            subprocess.run(["explorer", str(target)], check=True, timeout=15)
        else:
            subprocess.run(["xdg-open", str(target)], check=True, timeout=15)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ComputerControlError("Could not open the requested path.") from exc
    return {"action": "open_path", "path": str(target), "status": "ok"}


def take_screenshot(destination: str | None = None) -> dict:
    _require_enabled()
    try:
        import pyautogui
    except ImportError as exc:
        raise ComputerControlError("Screenshot support requires the pyautogui package.") from exc
    settings = get_settings()
    out_dir = settings.storage_path / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    if destination:
        out = Path(destination).expanduser()
        if not path_is_allowed(out):
            raise ComputerControlError("Screenshot destination is outside authorized directories.")
    else:
        from datetime import datetime, timezone
        out = out_dir / f"screenshot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.png"
    image = pyautogui.screenshot()
    image.save(out)
    return {"action": "screenshot", "path": str(out.resolve()), "status": "ok"}


def type_text(text: str) -> dict:
    _require_enabled()
    if not text or len(text) > 4_000:
        raise ComputerControlError("Typed text must be 1–4000 characters.")
    try:
        import pyautogui
    except ImportError as exc:
        raise ComputerControlError("Typing support requires the pyautogui package.") from exc
    pyautogui.write(text, interval=0.01)
    return {"action": "type_text", "characters": len(text), "status": "ok"}
