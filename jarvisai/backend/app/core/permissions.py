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


def path_is_allowed(target: str | Path) -> bool:
    try:
        resolved = Path(target).expanduser().resolve()
    except OSError:
        return False
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
