"""Accurate date/time and world clock (IANA timezones + common city aliases)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Common spoken place → IANA timezone
CITY_TIMEZONES: dict[str, str] = {
    "utc": "UTC",
    "gmt": "Etc/GMT",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid",
    "rome": "Europe/Rome",
    "moscow": "Europe/Moscow",
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "dhaka": "Asia/Dhaka",
    "bangladesh": "Asia/Dhaka",
    "bangkok": "Asia/Bangkok",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "tokyo": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "boston": "America/New_York",
    "washington": "America/New_York",
    "chicago": "America/Chicago",
    "denver": "America/Denver",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "cairo": "Africa/Cairo",
    "lagos": "Africa/Lagos",
    "nairobi": "Africa/Nairobi",
    "johannesburg": "Africa/Johannesburg",
}


class WorldTimeError(RuntimeError):
    pass


def _safe_display(dt: datetime) -> str:
    # Portable across macOS/Windows (avoid %-d / %-I).
    return f"{dt.strftime('%A, %B')} {dt.day}, {dt.year} · {dt.strftime('%I:%M:%S %p').lstrip('0')}"


def _format_instant(dt: datetime) -> dict[str, Any]:
    return {
        "iso": dt.isoformat(),
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "weekday": dt.strftime("%A"),
        "display": _safe_display(dt),
        "utc_offset": dt.strftime("%z"),
    }


def resolve_timezone(query: str | None, *, fallback: str | None = None) -> tuple[str, ZoneInfo]:
    raw = (query or "").strip()
    if not raw and fallback:
        raw = fallback
    if not raw:
        raise WorldTimeError("Provide a city or IANA timezone (e.g. Tokyo or Asia/Dhaka).")

    # Direct IANA
    try:
        return raw, ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        pass

    key = raw.lower().replace("_", " ").strip()
    if key in CITY_TIMEZONES:
        tz_name = CITY_TIMEZONES[key]
        return tz_name, ZoneInfo(tz_name)

    # Fuzzy: "time in new york" leftovers already cleaned by caller
    for city, tz_name in CITY_TIMEZONES.items():
        if city in key or key in city:
            return tz_name, ZoneInfo(tz_name)

    raise WorldTimeError(f"Unknown timezone or city “{query}”. Try an IANA name like Asia/Tokyo or a major city.")


def _host_timezone_name() -> str:
    """Best-effort IANA name for the host local zone."""
    local = datetime.now().astimezone()
    key = getattr(local.tzinfo, "key", None)
    if isinstance(key, str) and key:
        return key
    try:
        from pathlib import Path

        link = Path("/etc/localtime")
        if link.exists():
            target = str(link.resolve())
            marker = "/zoneinfo/"
            if marker in target:
                return target.split(marker, 1)[1]
    except OSError:
        pass
    return local.strftime("%Z") or local.strftime("%z") or "local"


def now_in_timezone(tz_name: str | None = None) -> dict[str, Any]:
    """Current accurate time. Default: host local timezone, plus UTC."""
    utc_now = datetime.now(timezone.utc)

    if tz_name:
        resolved, zi = resolve_timezone(tz_name)
        local = utc_now.astimezone(zi)
        label = resolved
    else:
        local = utc_now.astimezone()
        resolved = _host_timezone_name()
        label = resolved

    formatted = _format_instant(local)
    formatted["display"] = _safe_display(local)
    return {
        "action": "time.now",
        "timezone": resolved,
        "label": label,
        "source": "system clock (NTP-synced OS time)",
        "utc": {
            "iso": utc_now.isoformat(),
            "display": _safe_display(utc_now),
        },
        "local": formatted,
        "note": "This is the operating system clock, not an LLM estimate.",
    }


def world_clock(places: list[str] | None = None) -> dict[str, Any]:
    """Current time in one or more cities/timezones."""
    requested = [str(p).strip() for p in (places or []) if str(p).strip()]
    if not requested:
        requested = ["UTC", "America/New_York", "Europe/London", "Asia/Dhaka", "Asia/Tokyo"]
    if len(requested) > 12:
        raise WorldTimeError("Ask for at most 12 places at once.")

    utc_now = datetime.now(timezone.utc)
    clocks: list[dict[str, Any]] = []
    errors: list[str] = []
    for place in requested:
        try:
            tz_name, zi = resolve_timezone(place)
            local = utc_now.astimezone(zi)
            clocks.append({
                "query": place,
                "timezone": tz_name,
                "iso": local.isoformat(),
                "display": _safe_display(local),
                "weekday": local.strftime("%A"),
                "utc_offset": local.strftime("%z"),
            })
        except WorldTimeError as exc:
            errors.append(str(exc))

    if not clocks:
        raise WorldTimeError("; ".join(errors) or "No valid places.")

    return {
        "action": "time.world_clock",
        "as_of_utc": utc_now.isoformat(),
        "clocks": clocks,
        "errors": errors or None,
        "note": "Times from the OS clock with IANA timezones (DST-aware).",
    }


async def context_snapshot() -> dict[str, Any]:
    """Compact realtime facts to inject into chat (time + optional IP location)."""
    from app.core.permissions import live_web_enabled

    payload: dict[str, Any] = {
        "time": now_in_timezone(),
    }
    if live_web_enabled():
        try:
            from app.services.geolocation import resolve_ip_location

            payload["location"] = await resolve_ip_location()
        except Exception as exc:  # noqa: BLE001 — context must never break chat
            payload["location_error"] = str(exc)
    return payload
