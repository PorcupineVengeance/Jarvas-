"""Integration-ready calendar adapter. Returns unavailable until a provider is configured."""

from app.core.config import get_settings


class CalendarUnavailable(RuntimeError):
    pass


def provider_status() -> dict:
    return {
        "configured": False,
        "provider": None,
        "detail": "No calendar provider is connected. Add a Google Calendar or compatible adapter configuration to enable event operations.",
    }


async def list_events(_day: str | None = None) -> dict:
    raise CalendarUnavailable(provider_status()["detail"])


async def create_event(_payload: dict) -> dict:
    raise CalendarUnavailable(provider_status()["detail"])


async def update_event(_event_id: str, _payload: dict) -> dict:
    raise CalendarUnavailable(provider_status()["detail"])


async def delete_event(_event_id: str) -> dict:
    raise CalendarUnavailable(provider_status()["detail"])


def is_ready() -> bool:
    # Placeholder for future OAuth credentials (e.g. GOOGLE_CALENDAR_*).
    _ = get_settings()
    return False
