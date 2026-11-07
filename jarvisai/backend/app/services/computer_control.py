import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path

import psutil

from app.core.config import get_settings
from app.core.permissions import computer_control_enabled, full_device_access_enabled, path_is_allowed, user_home_root


class ComputerControlError(RuntimeError):
    pass


def _require_enabled() -> None:
    if not computer_control_enabled():
        raise ComputerControlError("Computer control is disabled. Enable it in Settings → Desktop permissions.")


def _require_full_device() -> None:
    _require_enabled()
    if not full_device_access_enabled():
        raise ComputerControlError(
            "Full device access is off. Enable “Full device access” in Settings → Desktop permissions "
            "(home folder, storage, and system settings)."
        )


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
        raise ComputerControlError("Path is outside authorized directories. Enable Full device access or add the folder in Settings.")
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


def storage_report() -> dict:
    """Disk + home-folder storage summary (real host metrics)."""
    _require_enabled()
    home = user_home_root()
    # Prefer the volume that holds the home directory.
    usage = shutil.disk_usage(str(home))
    partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            u = shutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        partitions.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "total_gb": round(u.total / (1024 ** 3), 2),
            "used_gb": round(u.used / (1024 ** 3), 2),
            "free_gb": round(u.free / (1024 ** 3), 2),
            "percent_used": round((u.used / u.total) * 100, 1) if u.total else None,
        })

    # Top-level home entries. Prefer `du -sk` (fast) when available; else names only.
    home_breakdown: list[dict] = []
    du_map: dict[str, float] = {}
    try:
        proc = subprocess.run(
            ["du", "-d", "1", "-k", str(home)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            for line in (proc.stdout or "").splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                try:
                    kb = int(parts[0].strip())
                except ValueError:
                    continue
                du_map[parts[1].strip()] = round(kb / (1024 ** 2), 2)  # GB
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        du_map = {}

    try:
        for child in sorted(home.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                size_gb = du_map.get(str(child))
                if size_gb is None and child.is_file():
                    size_gb = round(child.stat().st_size / (1024 ** 3), 3)
                home_breakdown.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "dir" if child.is_dir() else "file",
                    "size_gb": size_gb,
                })
            except OSError:
                continue
            if len(home_breakdown) >= 40:
                break
    except OSError:
        pass

    home_breakdown.sort(key=lambda row: float(row.get("size_gb") or 0), reverse=True)

    return {
        "action": "storage_report",
        "home": str(home),
        "full_device_access": full_device_access_enabled(),
        "volume": {
            "path": str(home),
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total else None,
        },
        "partitions": partitions[:12],
        "home_top_items": home_breakdown[:15],
        "note": "Live disk metrics from this computer. Home folder sizes are approximate.",
    }


def open_system_settings(section: str = "general") -> dict:
    """Open OS Settings / System Settings for the requested area."""
    # Settings panels only need computer control; home-wide files still need Full device access.
    _require_enabled()
    key = (section or "general").strip().lower()
    system = platform.system()

    mac_map = {
        "general": "x-apple.systempreferences:com.apple.SystemSettings.General",
        "storage": "x-apple.systempreferences:com.apple.settings.Storage",
        "network": "x-apple.systempreferences:com.apple.Network-Settings.extension",
        "bluetooth": "x-apple.systempreferences:com.apple.BluetoothSettings",
        "sound": "x-apple.systempreferences:com.apple.Sound-Settings.extension",
        "display": "x-apple.systempreferences:com.apple.Displays-Settings.extension",
        "privacy": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension",
        "microphone": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Microphone",
        "notifications": "x-apple.systempreferences:com.apple.Notifications-Settings.extension",
        "battery": "x-apple.systempreferences:com.apple.Battery-Settings.extension",
        "users": "x-apple.systempreferences:com.apple.Users-Groups-Settings.extension",
        "wallpaper": "x-apple.systempreferences:com.apple.Wallpaper-Settings.extension",
        "datetime": "x-apple.systempreferences:com.apple.Date-Time-Settings.extension",
    }
    win_map = {
        "general": "ms-settings:",
        "storage": "ms-settings:storagesense",
        "network": "ms-settings:network",
        "bluetooth": "ms-settings:bluetooth",
        "sound": "ms-settings:sound",
        "display": "ms-settings:display",
        "privacy": "ms-settings:privacy",
        "microphone": "ms-settings:privacy-microphone",
        "notifications": "ms-settings:notifications",
        "battery": "ms-settings:batterysaver",
        "users": "ms-settings:accounts",
        "wallpaper": "ms-settings:personalization-background",
        "datetime": "ms-settings:dateandtime",
        "apps": "ms-settings:appsfeatures",
    }

    try:
        if system == "Darwin":
            target = mac_map.get(key) or mac_map["general"]
            # Fallbacks for older macOS preference panes
            if key == "storage":
                subprocess.run(["open", "x-apple.systempreferences:com.apple.preferences.storage"], check=False, timeout=15)
            subprocess.run(["open", target], check=True, timeout=15)
        elif system == "Windows":
            target = win_map.get(key) or win_map["general"]
            subprocess.run(["cmd", "/c", "start", "", target], check=True, timeout=15, shell=False)
        else:
            # Best-effort Linux
            for cmd in (["gnome-control-center"], ["systemsettings5"], ["xdg-open", "settings://"]):
                try:
                    subprocess.run(cmd, check=True, timeout=15)
                    break
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            else:
                raise ComputerControlError("Could not open system settings on this Linux desktop.")
            target = "system-settings"
        return {"action": "open_system_settings", "section": key, "target": target if system != "Linux" else "system-settings", "status": "ok"}
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ComputerControlError(f"Could not open system settings for “{key}”.") from exc


def device_access_summary() -> dict:
    _require_enabled()
    home = user_home_root()
    settings = get_settings()
    return {
        "action": "device_access_summary",
        "computer_control": True,
        "full_device_access": full_device_access_enabled(),
        "home": str(home),
        "allowed_paths": [str(p) for p in settings.allowed_paths],
        "scope": (
            "Entire user home folder + settings/storage tools"
            if full_device_access_enabled()
            else "Only explicitly allowed folders"
        ),
        "note": "Destructive file deletes still require confirmation. Other users’ homes and protected system roots stay blocked.",
    }
