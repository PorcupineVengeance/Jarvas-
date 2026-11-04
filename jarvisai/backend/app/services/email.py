"""Integration-ready email adapter. Returns unavailable until a provider is configured."""

from app.core.config import get_settings


class EmailUnavailable(RuntimeError):
    pass


def provider_status() -> dict:
    return {
        "configured": False,
        "provider": None,
        "detail": "No email provider is connected. Configure a Gmail or compatible adapter before reading or sending mail.",
    }


async def list_messages(_query: str | None = None) -> dict:
    raise EmailUnavailable(provider_status()["detail"])


async def draft_reply(_message_id: str, _instructions: str) -> dict:
    raise EmailUnavailable(provider_status()["detail"])


async def send_message(_payload: dict) -> dict:
    raise EmailUnavailable(provider_status()["detail"])


def is_ready() -> bool:
    _ = get_settings()
    return False
