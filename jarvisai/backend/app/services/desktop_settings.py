"""Persist desktop permission preferences for the local sidecar."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.config import clear_settings_cache, get_settings


DEFAULT_ALLOWED = ["~/Desktop", "~/Documents", "~/Downloads"]
FULL_DEVICE_ALLOWED = [
    "~",
    "~/Desktop",
    "~/Documents",
    "~/Downloads",
    "~/Pictures",
    "~/Music",
    "~/Movies",
]


def settings_file() -> Path:
    settings = get_settings()
    if settings.jarvis_desktop_settings_path:
        return Path(settings.jarvis_desktop_settings_path).expanduser()
    env_path = os.getenv("JARVIS_DESKTOP_SETTINGS_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return settings.storage_path.parent / "desktop-settings.json"


def load_desktop_settings() -> dict[str, Any]:
    path = settings_file()
    settings = get_settings()
    # Desktop-first defaults: access on unless the JSON file explicitly disables it.
    defaults = {
        "computer_control": True if settings.is_desktop else bool(settings.jarvis_enable_computer_control),
        "live_web": bool(settings.jarvis_enable_live_web),
        "bluetooth": bool(settings.jarvis_enable_bluetooth),
        "full_device_access": True if settings.is_desktop else bool(settings.jarvis_enable_full_device_access),
        "allowed_paths": [str(p) for p in settings.jarvis_allowed_paths.split(",") if p.strip()]
        or list(FULL_DEVICE_ALLOWED if settings.is_desktop else DEFAULT_ALLOWED),
    }
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "computer_control": bool(data.get("computer_control", defaults["computer_control"])),
                    "live_web": bool(data.get("live_web", defaults["live_web"])),
                    "bluetooth": bool(data.get("bluetooth", defaults["bluetooth"])),
                    "full_device_access": bool(data.get("full_device_access", defaults["full_device_access"])),
                    "allowed_paths": list(data.get("allowed_paths") or defaults["allowed_paths"]),
                }
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return defaults


def save_desktop_settings(
    *,
    computer_control: bool,
    allowed_paths: list[str],
    live_web: bool = True,
    bluetooth: bool = False,
    full_device_access: bool = False,
) -> dict[str, Any]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in allowed_paths:
        raw = str(item).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        cleaned.append(raw)
    if full_device_access:
        # Ensure home-wide roots are present when full access is on.
        for item in FULL_DEVICE_ALLOWED:
            if item not in seen:
                cleaned.append(item)
                seen.add(item)
    if not cleaned:
        cleaned = list(DEFAULT_ALLOWED)
    payload = {
        "computer_control": bool(computer_control),
        "live_web": bool(live_web),
        "bluetooth": bool(bluetooth),
        "full_device_access": bool(full_device_access and computer_control),
        "allowed_paths": cleaned,
    }
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Apply immediately for the running process.
    os.environ["JARVIS_ENABLE_COMPUTER_CONTROL"] = "true" if computer_control else "false"
    os.environ["JARVIS_ENABLE_LIVE_WEB"] = "true" if live_web else "false"
    os.environ["JARVIS_ENABLE_BLUETOOTH"] = "true" if bluetooth else "false"
    os.environ["JARVIS_ENABLE_FULL_DEVICE_ACCESS"] = "true" if payload["full_device_access"] else "false"
    os.environ["JARVIS_ALLOWED_PATHS"] = ",".join(cleaned)
    clear_settings_cache()
    return payload


def apply_desktop_settings_on_boot() -> None:
    """Overlay JSON preferences onto process env before first settings read."""
    sync_desktop_settings_from_disk()


def sync_desktop_settings_from_disk() -> dict[str, Any]:
    """Re-read desktop-settings.json into process env (call every chat turn)."""
    if os.getenv("JARVIS_DESKTOP") != "1":
        return {}
    clear_settings_cache()
    data = load_desktop_settings()
    # Desktop defaults: computer control on; full home access on unless explicitly disabled.
    computer = bool(data.get("computer_control", True))
    live_web = bool(data.get("live_web", True))
    bluetooth = bool(data.get("bluetooth", False))
    full_device = bool(data.get("full_device_access", True)) if computer else False
    os.environ["JARVIS_ENABLE_COMPUTER_CONTROL"] = "true" if computer else "false"
    os.environ["JARVIS_ENABLE_LIVE_WEB"] = "true" if live_web else "false"
    os.environ["JARVIS_ENABLE_BLUETOOTH"] = "true" if bluetooth else "false"
    os.environ["JARVIS_ENABLE_FULL_DEVICE_ACCESS"] = "true" if full_device and computer else "false"
    paths = data.get("allowed_paths") or list(FULL_DEVICE_ALLOWED if full_device else DEFAULT_ALLOWED)
    os.environ["JARVIS_ALLOWED_PATHS"] = ",".join(str(p) for p in paths)
    clear_settings_cache()
    return {
        "computer_control": computer,
        "live_web": live_web,
        "bluetooth": bluetooth,
        "full_device_access": full_device and computer,
        "allowed_paths": list(paths),
    }
