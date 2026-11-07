"""Approximate location from this machine's public IP (privacy: city-level only)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.permissions import live_web_enabled


class GeolocationError(RuntimeError):
    pass


def _require_live() -> None:
    if not live_web_enabled():
        raise GeolocationError("Live web is disabled. Enable Live web & weather in Settings.")


async def resolve_ip_location() -> dict[str, Any]:
    """Return approximate city/region/country/timezone for this host's outbound IP."""
    _require_live()
    headers = {"User-Agent": "JARVIS-Location/1.0", "Accept": "application/json"}
    errors: list[str] = []

    # ipapi.co — HTTPS, no key for light use
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=True, headers=headers) as client:
            resp = await client.get("https://ipapi.co/json/")
            if not resp.is_error:
                data = resp.json()
                if isinstance(data, dict) and not data.get("error"):
                    city = str(data.get("city") or "").strip()
                    region = str(data.get("region") or data.get("region_code") or "").strip()
                    country = str(data.get("country_name") or data.get("country") or "").strip()
                    timezone = str(data.get("timezone") or "").strip()
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    ip = str(data.get("ip") or "").strip()
                    label = ", ".join(part for part in (city, region, country) if part) or "Unknown"
                    return {
                        "provider": "ipapi.co",
                        "ip": ip or None,
                        "label": label,
                        "city": city or None,
                        "region": region or None,
                        "country": country or None,
                        "timezone": timezone or None,
                        "latitude": float(lat) if isinstance(lat, (int, float)) else None,
                        "longitude": float(lon) if isinstance(lon, (int, float)) else None,
                        "accuracy": "city-level approximate (public IP)",
                        "note": "Location is inferred from this computer's public IP, not GPS.",
                    }
            errors.append(f"ipapi.co HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        errors.append(f"ipapi.co: {exc}")

    # Fallback: ip-api.com (HTTP)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=True, headers=headers) as client:
            resp = await client.get("http://ip-api.com/json/?fields=status,message,country,regionName,city,lat,lon,timezone,query")
            if not resp.is_error:
                data = resp.json()
                if isinstance(data, dict) and data.get("status") == "success":
                    city = str(data.get("city") or "").strip()
                    region = str(data.get("regionName") or "").strip()
                    country = str(data.get("country") or "").strip()
                    timezone = str(data.get("timezone") or "").strip()
                    label = ", ".join(part for part in (city, region, country) if part) or "Unknown"
                    return {
                        "provider": "ip-api.com",
                        "ip": str(data.get("query") or "") or None,
                        "label": label,
                        "city": city or None,
                        "region": region or None,
                        "country": country or None,
                        "timezone": timezone or None,
                        "latitude": float(data["lat"]) if isinstance(data.get("lat"), (int, float)) else None,
                        "longitude": float(data["lon"]) if isinstance(data.get("lon"), (int, float)) else None,
                        "accuracy": "city-level approximate (public IP)",
                        "note": "Location is inferred from this computer's public IP, not GPS.",
                    }
            errors.append(f"ip-api.com HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        errors.append(f"ip-api.com: {exc}")

    raise GeolocationError("Could not resolve location from public IP. " + "; ".join(errors[:2]))
