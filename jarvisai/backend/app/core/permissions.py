from pathlib import Path
from app.core.config import get_settings


SENSITIVE_ACTIONS = {
    "file.delete",
    "file.rename",
    "computer.type",
    "computer.click",
    "browser.navigate",
    "email.send",
    "calendar.delete",
}


def computer_control_enabled() -> bool:
    return bool(get_settings().jarvis_enable_computer_control)


def live_web_enabled() -> bool:
    """User-permissioned live web research, page fetch, and weather."""
    return bool(get_settings().jarvis_enable_live_web)


def bluetooth_control_enabled() -> bool:
    """User-permissioned Bluetooth accessory control (Desktop)."""
    return bool(get_settings().jarvis_enable_bluetooth)


def full_device_access_enabled() -> bool:
    """User opted in to home-wide files + settings/storage helpers (Desktop)."""
    settings = get_settings()
    return bool(settings.jarvis_enable_computer_control and settings.jarvis_enable_full_device_access)


def user_home_root() -> Path:
    return Path.home().resolve()


def path_is_allowed(target: str | Path) -> bool:
    try:
        resolved = Path(target).expanduser().resolve()
    except OSError:
        return False
    # Full device access → entire user home (not other users / system roots).
    if full_device_access_enabled():
        home = user_home_root()
        try:
            resolved.relative_to(home)
            return True
        except ValueError:
            pass
    allowed = get_settings().allowed_paths
    if not allowed:
        return False
    for root in allowed:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def require_confirmation(tool_id: str, confirmed: bool) -> bool:
    definition_write = tool_id in SENSITIVE_ACTIONS or tool_id.endswith(".delete") or tool_id.endswith(".send")
    if definition_write and not confirmed:
        return False
    return True
