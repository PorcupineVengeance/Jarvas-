from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User
from app.services.desktop_settings import load_desktop_settings, save_desktop_settings

router = APIRouter(prefix="/api/desktop", tags=["desktop"])


class DesktopSettingsUpdate(BaseModel):
    computer_control: bool = True
    live_web: bool = True
    bluetooth: bool = False
    allowed_paths: list[str] = Field(default_factory=lambda: ["~/Desktop", "~/Documents", "~/Downloads"], max_length=32)


@router.get("/info")
def desktop_info(_user: User = Depends(get_current_user)):
    settings = get_settings()
    prefs = load_desktop_settings() if settings.is_desktop else None
    downloads = settings.desktop_download_urls
    return {
        "is_desktop": settings.is_desktop,
        "computer_control": bool(settings.jarvis_enable_computer_control) if settings.is_desktop else False,
        "live_web": bool(settings.jarvis_enable_live_web),
        "bluetooth": bool(settings.jarvis_enable_bluetooth) if settings.is_desktop else False,
        "allowed_paths": [str(p) for p in settings.allowed_paths] if settings.is_desktop else [],
        "preferences": prefs,
        "downloads": {
            "mac": downloads.get("mac") or None,
            "windows": downloads.get("windows") or None,
            "configured": bool(downloads.get("configured")),
            "base": downloads.get("base"),
        },
        "notice": (
            "Desktop JARVIS can open apps, browse URLs, use live web/weather, and control Bluetooth when you allow those permissions."
            if settings.is_desktop
            else "Install JARVIS Desktop to let the assistant help with apps and files on this computer."
        ),
    }


@router.get("/settings")
def get_settings_route(_user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.is_desktop:
        raise HTTPException(status_code=400, detail="Desktop settings are only available inside JARVIS Desktop.")
    return load_desktop_settings()


@router.put("/settings")
def update_settings(body: DesktopSettingsUpdate, _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.is_desktop:
        raise HTTPException(status_code=400, detail="Desktop settings are only available inside JARVIS Desktop.")
    if len(body.allowed_paths) > 32:
        raise HTTPException(status_code=422, detail="Too many allowed folders.")
    for path in body.allowed_paths:
        if len(path) > 500 or "\x00" in path:
            raise HTTPException(status_code=422, detail="An allowed path is invalid.")
    saved = save_desktop_settings(
        computer_control=body.computer_control,
        allowed_paths=body.allowed_paths,
        live_web=body.live_web,
        bluetooth=body.bluetooth,
    )
    return {"ok": True, **saved, "applied": True, "message": "Permissions updated for this desktop session."}
